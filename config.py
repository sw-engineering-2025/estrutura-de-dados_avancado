"""Configuracao das filiais e do transporte fisico (pen drive)."""

import os
from pathlib import Path

FILIAIS = {
    1: "Maricá",
    2: "Niterói",
}

# Chave pre-compartilhada: combinada presencialmente entre as duas filiais,
# guardada em variavel de ambiente e NUNCA gravada no pen drive.
#   export MSGX_CHAVE="a chave combinada"
CHAVE_PADRAO = "chave-de-demonstracao-dress-to-2026"
CHAVE = os.environ.get("MSGX_CHAVE", CHAVE_PADRAO)

# Simula o pen drive. Na pratica, apontar para o ponto de montagem real,
# por exemplo /media/leonardo/PENDRIVE.
PENDRIVE = Path(os.environ.get("MSGX_PENDRIVE", "./pendrive"))

# Historico local da filial. NUNCA dentro da pasta do pen drive.
HISTORICO = Path(os.environ.get("MSGX_HISTORICO", "./historico.db"))

EXTENSAO = ".msgx"

# Historico local da filial (SQLite). Fica na maquina da filial e NUNCA dentro
# da pasta do pen drive. Com duas filiais na mesma maquina, use um arquivo
# para cada:  MSGX_HISTORICO=marica.db  /  MSGX_HISTORICO=niteroi.db
HISTORICO = Path(os.environ.get("MSGX_HISTORICO", "./historico.db"))

# Limite de caracteres que a IA usa como alvo ao resumir ("mensagens curtas").
LIMITE_MENSAGEM_CURTA = 180


def nome_filial(codigo: int) -> str:
    return FILIAIS.get(codigo, f"Desconhecida({codigo})")


def garantir_pendrive() -> Path:
    PENDRIVE.mkdir(parents=True, exist_ok=True)
    return PENDRIVE
