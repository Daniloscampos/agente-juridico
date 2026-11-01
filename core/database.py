from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
from core.config import settings

engine = create_engine(settings.DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class Execucao(Base):
    __tablename__ = "execucoes"
    id = Column(Integer, primary_key=True)
    data_hora = Column(DateTime, default=datetime.utcnow)
    processo = Column(String(30), index=True)
    tarefa = Column(String(255))
    origem = Column(String(50))          # INTEGRA, manual, etc.
    acao = Column(String(120))
    resultado = Column(String(30))       # sucesso, erro, aguardando_aprovacao
    arquivo_gerado = Column(String(500))
    local_salvo = Column(String(500))
    mensagem = Column(Text)
    erro = Column(Text)

def init_db():
    Base.metadata.create_all(bind=engine)

def registrar_execucao(**kwargs):
    with SessionLocal() as s:
        s.add(Execucao(**kwargs))
        s.commit()