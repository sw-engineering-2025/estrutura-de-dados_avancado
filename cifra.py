"""
Camada de cifra.

A arvore de Huffman resolve a COMPRESSAO. Ela nao resolve o sigilo: quem
pegasse o pen drive no meio do caminho teria a tabela de frequencias e
remontaria a arvore sozinho. Por isso o bloco sensivel do arquivo e cifrado
com uma chave que existe apenas nas duas filiais e nunca viaja no pen drive.

O keystream e derivado por SHA-256 em modo contador:

    bloco_i = SHA256( chave || nonce || i )
    keystream = bloco_0 || bloco_1 || bloco_2 ...

e a cifra e um XOR byte a byte entre os dados e esse keystream.

Detalhe que vale defender na banca: o nonce e o MSG_ID (UUID4) do arquivo.
Sem ele, duas mensagens cifradas com a mesma chave usariam o mesmo
keystream, e o XOR de uma com a outra eliminaria a chave da equacao
(o classico "two-time pad"). Com nonce por mensagem, isso nao acontece.
"""

import hashlib
import zlib


def derivar_keystream(chave: str, nonce: bytes, tamanho: int) -> bytes:
    """Gera 'tamanho' bytes pseudoaleatorios a partir de (chave, nonce)."""
    base = chave.encode("utf-8") + nonce
    fluxo = bytearray()
    contador = 0
    while len(fluxo) < tamanho:
        fluxo += hashlib.sha256(base + contador.to_bytes(8, "big")).digest()
        contador += 1
    return bytes(fluxo[:tamanho])


def cifrar(dados: bytes, chave: str, nonce: bytes) -> bytes:
    """XOR com o keystream. A mesma funcao cifra e decifra (XOR e involutivo)."""
    keystream = derivar_keystream(chave, nonce, len(dados))
    return bytes(d ^ k for d, k in zip(dados, keystream))


decifrar = cifrar


def calcular_crc(dados: bytes) -> int:
    """Checksum de integridade -- pen drive cai no chao, setor corrompe."""
    return zlib.crc32(dados) & 0xFFFFFFFF


def impressao_digital(chave: str) -> str:
    """
    Identificador curto da chave, para a filial de destino conferir que esta
    usando a mesma chave da origem sem precisar exibir a chave em si.
    """
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()[:8].upper()
