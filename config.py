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

EXTENSAO = ".msgx"

# Limite de caracteres que a IA usa como alvo ao resumir ("mensagens curtas").
LIMITE_MENSAGEM_CURTA = 180


def nome_filial(codigo: int) -> str:
    return FILIAIS.get(codigo, f"Desconhecida({codigo})")


def garantir_pendrive() -> Path:
    PENDRIVE.mkdir(parents=True, exist_ok=True)
    return PENDRIVE
