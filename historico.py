"""
Historico local de mensagens da filial, em SQLite (biblioteca padrao).

O que se grava e o proprio arquivo .msgx, AINDA CIFRADO, num campo BLOB.
Em colunas normais ficam so os dados do envelope -- origem, destino, data e
id --, que ja viajam em claro no pen drive de qualquer forma. Consequencia:

  - a lista do historico aparece sem precisar da chave;
  - para ler o texto, o BLOB passa pelo mesmo formato.desempacotar() de uma
    remessa recem-chegada, e a chave e exigida;
  - quem copiar o historico.db fica na mesma situacao de quem achou o pen
    drive. O historico nao abre um caminho novo de vazamento.
"""

import sqlite3
import time
from contextlib import closing

import config
import formato

ENVIADA = "enviada"
RECEBIDA = "recebida"

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS mensagens (
    msg_id        TEXT    NOT NULL,
    direcao       TEXT    NOT NULL CHECK (direcao IN ('enviada', 'recebida')),
    origem        INTEGER NOT NULL,
    destino       INTEGER NOT NULL,
    criada_em     INTEGER NOT NULL,   -- epoch do envelope (quando foi lacrada)
    registrada_em INTEGER NOT NULL,   -- epoch de quando entrou neste historico
    arquivo       BLOB    NOT NULL,   -- o .msgx inteiro, ainda cifrado
    PRIMARY KEY (msg_id, direcao)
)
"""


def _conectar() -> sqlite3.Connection:
    # Uma conexao por operacao: o web.py atende cada requisicao numa thread,
    # e uma conexao SQLite, por padrao, nao pode ser usada em outra thread.
    conexao = sqlite3.connect(config.HISTORICO)
    conexao.row_factory = sqlite3.Row
    conexao.execute(_ESQUEMA)
    return conexao


def registrar(direcao: str, arquivo: bytes) -> None:
    """
    Guarda a remessa. Os metadados saem do proprio envelope, entao o arquivo
    precisa ser um .msgx valido (CRC conferido). Registrar de novo a mesma
    mensagem na mesma direcao nao duplica nada.
    """
    envelope = formato.ler_envelope(arquivo)

    # `with conexao` faz commit (ou rollback) da transacao, mas NAO fecha a
    # conexao -- quem fecha e o closing().
    with closing(_conectar()) as conexao, conexao:
        conexao.execute(
            "INSERT OR IGNORE INTO mensagens "
            "(msg_id, direcao, origem, destino, criada_em, registrada_em, arquivo) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(envelope["msg_id"]),
                direcao,
                envelope["origem"],
                envelope["destino"],
                int(envelope["timestamp"].timestamp()),
                int(time.time()),
                arquivo,
            ),
        )


def listar(limite: int = 50) -> list[dict]:
    """Mensagens mais recentes primeiro, sem o BLOB (so o envelope)."""
    with closing(_conectar()) as conexao:
        linhas = conexao.execute(
            "SELECT msg_id, direcao, origem, destino, criada_em, registrada_em, "
            "       length(arquivo) AS bytes "
            "FROM mensagens ORDER BY criada_em DESC, registrada_em DESC LIMIT ?",
            (limite,),
        ).fetchall()
    return [dict(linha) for linha in linhas]


def obter_arquivo(msg_id: str, direcao: str) -> bytes | None:
    """Devolve o .msgx guardado, pronto para formato.desempacotar()."""
    with closing(_conectar()) as conexao:
        linha = conexao.execute(
            "SELECT arquivo FROM mensagens WHERE msg_id = ? AND direcao = ?",
            (msg_id, direcao),
        ).fetchone()
    return bytes(linha["arquivo"]) if linha else None
