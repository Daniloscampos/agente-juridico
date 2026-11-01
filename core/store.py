"""SQLite, one worker, local POC. PostgreSQL required before horizontal scaling."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS whatsapp_cursor(id INTEGER PRIMARY KEY CHECK(id=1), seq INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS whatsapp_outbox(seq INTEGER NOT NULL, username TEXT NOT NULL,
                state TEXT NOT NULL, created TEXT NOT NULL, message_id TEXT NOT NULL DEFAULT '', PRIMARY KEY(seq,username));
            CREATE TABLE IF NOT EXISTS control(id INTEGER PRIMARY KEY CHECK(id=1),
                paused INTEGER NOT NULL, mode TEXT NOT NULL);
            INSERT OR IGNORE INTO control VALUES(1,1,'pausado');
            CREATE TABLE IF NOT EXISTS limits(action TEXT PRIMARY KEY, review INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS runs(task_key TEXT PRIMARY KEY, task_id TEXT NOT NULL,
                process TEXT NOT NULL, status TEXT NOT NULL, updated TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS steps(step_key TEXT PRIMARY KEY, state TEXT NOT NULL,
                result TEXT NOT NULL DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS deliveries(run_key TEXT PRIMARY KEY, manifest TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reviews(run_key TEXT PRIMARY KEY, actor TEXT NOT NULL,
                decision TEXT NOT NULL, comment TEXT NOT NULL, reviewed TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL);
            """)

    @contextmanager
    def db(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA journal_mode=WAL")
            with c:
                yield c
        finally:
            c.close()

    def control(self):
        with self.db() as c:
            return dict(c.execute("SELECT * FROM control WHERE id=1").fetchone())

    def set_pause(self, paused: bool, actor: str):
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("UPDATE control SET paused=?, mode=? WHERE id=1",
                      (int(paused), "pausado" if paused else "operando"))
            self._audit(c, {"action": "pausa" if paused else "retomada", "actor": actor,
                            "result": "confirmado"})

    def requires_review(self, action):
        with self.db() as c:
            row = c.execute("SELECT review FROM limits WHERE action=?", (action,)).fetchone()
            return bool(row and row[0])

    def critical_error(self, code):
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("UPDATE control SET paused=1,mode='erro' WHERE id=1")
            self._audit(c, {"action": "erro_critico", "error": code, "result": "bloqueado"})

    def limit(self, action, review, actor):
        from core.policy import AUTO, Blocked
        if action not in AUTO:
            raise Blocked("LIMITE_INVALIDO")
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("INSERT INTO limits VALUES(?,?) ON CONFLICT(action) DO UPDATE SET review=excluded.review",
                      (action, int(review)))
            self._audit(c, {"action": "alterar_limite", "limited_action": action,
                            "review": review, "actor": actor, "result": "confirmado"})

    def start_run(self, key, task_id, process):
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            cursor = c.execute("INSERT OR IGNORE INTO runs VALUES(?,?,?,'executando',?)",
                               (key, task_id, process, now()))
            if cursor.rowcount == 1:
                return True
            # Only a cooperative pause can resume automatically. Uncertain writes cannot.
            resumed = c.execute("UPDATE runs SET status='executando',updated=? WHERE task_key=? AND status='pausado_reconciliar'", (now(), key))
            return resumed.rowcount == 1

    def finish(self, key, status):
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            updated=c.execute("UPDATE runs SET status=?,updated=? WHERE task_key=? AND status!=?", (status, now(), key, status))
            if updated.rowcount:
                self._audit(c,{"action":"finalizar","run":key,"result":status})

    def record_delivery(self, key, files):
        from core.policy import Blocked
        manifest = []
        for item in files:
            path = Path(item["file"])
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != item["sha256"]:
                raise Blocked("ARQUIVO_ALTERADO_ANTES_DA_ENTREGA")
            manifest.append({"file": str(path.resolve()), "sha256": digest})
        with self.db() as c:
            c.execute("INSERT OR REPLACE INTO deliveries VALUES(?,?)", (key, json.dumps(manifest)))

    def review_run(self, key, actor, decision, comment=""):
        from core.policy import Blocked
        if not actor.strip() or decision not in {"revisado", "correcao_solicitada"}:
            raise Blocked("REVISAO_INVALIDA")
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            run = c.execute("SELECT status FROM runs WHERE task_key=?", (key,)).fetchone()
            delivery = c.execute("SELECT manifest FROM deliveries WHERE run_key=?", (key,)).fetchone()
            if not run or run[0] != "aguardando_revisao" or not delivery:
                raise Blocked("ENTREGA_NAO_DISPONIVEL_PARA_REVISAO")
            for item in json.loads(delivery[0]):
                path = Path(item["file"])
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                    raise Blocked("VERSAO_DA_ENTREGA_ALTERADA")
            c.execute("INSERT OR REPLACE INTO reviews VALUES(?,?,?,?,?)", (key, actor, decision, comment, now()))
            c.execute("UPDATE runs SET status=?,updated=? WHERE task_key=?", (decision, now(), key))
            self._audit(c, {"action": "revisao_entrega", "run": key, "actor": actor,
                            "result": decision, "comment": comment})
        return {"status": decision, "note": "Revisao registrada; nao autoriza assinatura, pagamento ou protocolo"}

    def reserve_step(self, key):
        # Reserves intent before external mutation. A crash after this point
        # leaves 'started', forcing manual reconciliation on next attempt.
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT * FROM steps WHERE step_key=?", (key,)).fetchone()
            if row:
                return dict(row)
            c.execute("INSERT INTO steps(step_key,state) VALUES(?,'started')", (key,))
            return None

    def complete_step(self, key, result):
        with self.db() as c:
            c.execute("UPDATE steps SET state='done',result=? WHERE step_key=?",
                      (json.dumps(result, ensure_ascii=False), key))

    def event(self, **data):
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            self._audit(c, data)

    def _audit(self, c, data):
        payload = json.dumps({"time": now(), **data}, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"))
        previous = c.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        previous = previous[0] if previous else "0" * 64
        digest = hashlib.sha256((previous + payload).encode()).hexdigest()
        c.execute("INSERT INTO audit(payload,previous_hash,hash) VALUES(?,?,?)", (payload, previous, digest))

    def verify(self):
        previous = "0" * 64
        with self.db() as c:
            for row in c.execute("SELECT * FROM audit ORDER BY seq"):
                expected = hashlib.sha256((previous + row["payload"]).encode()).hexdigest()
                if row["previous_hash"] != previous or row["hash"] != expected:
                    return False
                previous = row["hash"]
        return True

    def snapshot(self):
        with self.db() as c:
            runs = [dict(r) for r in c.execute("SELECT * FROM runs ORDER BY updated DESC LIMIT 100")]
            audit = [{"seq": r["seq"], **json.loads(r["payload"]), "hash": r["hash"]}
                     for r in c.execute("SELECT * FROM audit ORDER BY seq DESC LIMIT 100")]
            limits = {r[0]: bool(r[1]) for r in c.execute("SELECT action,review FROM limits")}
            totals = dict(c.execute("SELECT status,COUNT(*) FROM runs GROUP BY status").fetchall())
        return {"control": self.control(), "metrics": totals, "runs": runs, "audit": audit, "limits": limits}
