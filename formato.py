"""
Formato de arquivo .msgx -- o "formato dos dados" do trabalho.

Layout (big-endian):

  [ EM CLARO ]
  MAGIC      4 bytes   b"MSGX"
  VERSAO     1 byte    0x01
  ORIGEM     1 byte    codigo da filial remetente
  DESTINO    1 byte    codigo da filial destinataria
  MSG_ID    16 bytes   UUID4 -- tambem usado como nonce da cifra
  TIMESTAMP  8 bytes   uint64, epoch em segundos
  TAM_BLOCO  4 bytes   uint32, tamanho do bloco cifrado

  [ CIFRADO COM A CHAVE PRE-COMPARTILHADA ]
  N_SIMB     1 byte    quantidade de simbolos distintos, gravada como n-1
                       (permite representar de 1 a 256 simbolos em 1 byte)
  TABELA     n x 3     simbolo (1 byte) + frequencia (2 bytes, uint16)
  N_BITS     4 bytes   uint32, quantidade de bits uteis do payload
  PAYLOAD    ceil(N_BITS/8) bytes -- bitstream da arvore de Huffman

  [ EM CLARO ]
  CRC32      4 bytes   sobre todos os bytes anteriores

Por que a tabela de frequencias fica DENTRO da parte cifrada: se viajasse em
claro, quem achasse o pen drive ja saberia o alfabeto usado e o tamanho da
mensagem, mesmo sem conseguir ler o texto. Em claro fica so o roteamento
(origem, destino, data) -- o equivalente ao envelope de uma carta.
"""

import struct
import uuid
from datetime import datetime, timezone

import cifra
import huffman

MAGIC = b"MSGX"
VERSAO = 1

_CABECALHO = struct.Struct(">4sBBB16sQI")   # 35 bytes
_TAM_CRC = 4


def empacotar(texto: str, chave: str, codigo_origem: int, codigo_destino: int) -> dict:
    """
    Executa o pipeline completo da origem e devolve os bytes do arquivo mais
    as estatisticas usadas na tela e no relatorio.
    """
    dados = texto.encode("utf-8")
    if not dados:
        raise ValueError("Mensagem vazia.")

    frequencias = huffman.contar_frequencias(dados)
    if max(frequencias.values()) > 0xFFFF:
        raise ValueError("Mensagem longa demais para o formato (frequência > 65535).")

    raiz = huffman.construir_arvore(frequencias)
    codigos = huffman.gerar_codigos(raiz)
    payload, n_bits = huffman.codificar(dados, codigos)

    # Bloco sensivel: tabela + tamanho + bitstream
    bloco = bytearray()
    bloco.append(len(frequencias) - 1)
    for simbolo in sorted(frequencias):
        bloco += struct.pack(">BH", simbolo, frequencias[simbolo])
    bloco += struct.pack(">I", n_bits)
    bloco += payload

    msg_id = uuid.uuid4().bytes
    bloco_cifrado = cifra.cifrar(bytes(bloco), chave, msg_id)

    cabecalho = _CABECALHO.pack(
        MAGIC,
        VERSAO,
        codigo_origem,
        codigo_destino,
        msg_id,
        int(datetime.now(timezone.utc).timestamp()),
        len(bloco_cifrado),
    )

    corpo = cabecalho + bloco_cifrado
    arquivo = corpo + struct.pack(">I", cifra.calcular_crc(corpo))

    return {
        "arquivo": arquivo,
        "msg_id": uuid.UUID(bytes=msg_id),
        "bits_originais": len(dados) * 8,
        "bits_comprimidos": n_bits,
        "tamanho_arquivo": len(arquivo),
        "codigos": codigos,
        "raiz": raiz,
        "frequencias": frequencias,
    }


def ler_envelope(arquivo: bytes) -> dict:
    """
    Le apenas a parte em claro e valida o CRC -- sem chave nenhuma.
    E exatamente o que um invasor consegue extrair do pen drive perdido.
    """
    if len(arquivo) < _CABECALHO.size + _TAM_CRC:
        raise ValueError("Arquivo truncado ou corrompido.")

    magic, versao, origem, destino, msg_id, timestamp, tam_bloco = _CABECALHO.unpack(
        arquivo[:_CABECALHO.size]
    )
    if magic != MAGIC:
        raise ValueError("Arquivo não está no formato .msgx.")
    if versao != VERSAO:
        raise ValueError(f"Versão de formato não suportada: {versao}.")

    esperado = _CABECALHO.size + tam_bloco + _TAM_CRC
    if len(arquivo) != esperado:
        raise ValueError("Tamanho do arquivo não confere com o cabeçalho.")

    corpo = arquivo[:-_TAM_CRC]
    crc_gravado = struct.unpack(">I", arquivo[-_TAM_CRC:])[0]
    if cifra.calcular_crc(corpo) != crc_gravado:
        raise ValueError("CRC inválido: arquivo corrompido no transporte.")

    return {
        "versao": versao,
        "origem": origem,
        "destino": destino,
        "msg_id": uuid.UUID(bytes=msg_id),
        "timestamp": datetime.fromtimestamp(timestamp, timezone.utc),
        "tamanho_bloco": tam_bloco,
        "bloco_cifrado": arquivo[_CABECALHO.size:-_TAM_CRC],
        "msg_id_bytes": msg_id,
    }


def desempacotar(arquivo: bytes, chave: str) -> dict:
    """
    Pipeline do destino: valida, decifra, REFAZ A ARVORE a partir da tabela
    de frequencias e percorre o bitstream para recuperar o texto.
    """
    envelope = ler_envelope(arquivo)
    bloco = cifra.decifrar(envelope["bloco_cifrado"], chave, envelope["msg_id_bytes"])

    try:
        n_simbolos = bloco[0] + 1
        posicao = 1
        frequencias = {}
        for _ in range(n_simbolos):
            simbolo, frequencia = struct.unpack(">BH", bloco[posicao:posicao + 3])
            frequencias[simbolo] = frequencia
            posicao += 3
        n_bits = struct.unpack(">I", bloco[posicao:posicao + 4])[0]
        posicao += 4
        payload = bloco[posicao:]

        if len(payload) != -(-n_bits // 8):
            raise ValueError

        raiz = huffman.construir_arvore(frequencias)          # <- a arvore renasce aqui
        dados = huffman.decodificar(payload, n_bits, raiz)
        texto = dados.decode("utf-8")
    except (ValueError, struct.error, IndexError, UnicodeDecodeError, KeyError):
        raise ValueError(
            "Não foi possível abrir a mensagem. A chave desta filial provavelmente "
            "não confere com a da filial de origem."
        )

    envelope.update({
        "texto": texto,
        "raiz": raiz,
        "frequencias": frequencias,
        "n_bits": n_bits,
        "codigos": huffman.gerar_codigos(raiz),
    })
    return envelope
