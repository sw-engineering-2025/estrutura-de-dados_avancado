"""
Arvore de Huffman.

A arvore e montada sobre BYTES (a mensagem e convertida para UTF-8 antes),
e nao sobre caracteres. Isso faz acento, cedilha e emoji funcionarem sem
tratamento especial, e mantem o alfabeto sempre no intervalo 0..255.

Ponto critico do trabalho: a arvore precisa ser reconstruida IDENTICA na
filial de destino, a partir apenas da tabela de frequencias. Por isso todo
empate de frequencia e desempatado de forma deterministica (ver
construir_arvore).
"""

import heapq
from collections import Counter


class No:
    """No da arvore binaria. Folhas carregam simbolo; internos carregam None."""

    __slots__ = ("simbolo", "frequencia", "esquerda", "direita")

    def __init__(self, frequencia, simbolo=None, esquerda=None, direita=None):
        self.frequencia = frequencia
        self.simbolo = simbolo
        self.esquerda = esquerda
        self.direita = direita

    @property
    def eh_folha(self):
        return self.esquerda is None and self.direita is None

    def __repr__(self):
        if self.eh_folha:
            return f"Folha({self.simbolo!r}, {self.frequencia})"
        return f"No({self.frequencia})"


def contar_frequencias(dados: bytes) -> dict:
    """Conta quantas vezes cada byte aparece na mensagem."""
    return dict(Counter(dados))


def construir_arvore(frequencias: dict) -> No:
    """
    Monta a arvore de Huffman com uma fila de prioridade (min-heap).

    O determinismo vem de dois cuidados:
      1. As folhas entram no heap em ordem crescente de simbolo.
      2. O heap guarda (frequencia, ordem_de_insercao, no) -- assim dois nos
         de mesma frequencia SEMPRE saem na mesma ordem, dos dois lados.

    Sem isso, origem e destino montariam arvores diferentes e a leitura
    devolveria lixo.
    """
    if not frequencias:
        raise ValueError("Mensagem vazia: não há frequências para montar a árvore.")

    heap = []
    ordem = 0
    for simbolo in sorted(frequencias):
        no = No(frequencias[simbolo], simbolo)
        heapq.heappush(heap, (no.frequencia, ordem, no))
        ordem += 1

    # Caso de borda: mensagem com um unico simbolo distinto ("aaaa").
    # Criamos uma raiz artificial para que esse simbolo tenha o codigo "0".
    if len(heap) == 1:
        frequencia, _, unico = heap[0]
        return No(frequencia, None, unico, None)

    while len(heap) > 1:
        freq_a, _, no_a = heapq.heappop(heap)
        freq_b, _, no_b = heapq.heappop(heap)
        interno = No(freq_a + freq_b, None, no_a, no_b)
        heapq.heappush(heap, (interno.frequencia, ordem, interno))
        ordem += 1

    return heap[0][2]


def gerar_codigos(raiz: No) -> dict:
    """
    Percorre a arvore da raiz ate cada folha montando o codigo binario.
    Esquerda = 0, direita = 1. Retorna {byte: "0101..."}.
    """
    codigos = {}
    pilha = [(raiz, "")]
    while pilha:
        no, caminho = pilha.pop()
        if no.eh_folha:
            codigos[no.simbolo] = caminho or "0"
            continue
        if no.direita is not None:
            pilha.append((no.direita, caminho + "1"))
        if no.esquerda is not None:
            pilha.append((no.esquerda, caminho + "0"))
    return codigos


def codificar(dados: bytes, codigos: dict):
    """
    Troca cada byte pelo seu codigo binario e empacota o resultado em bytes.

    Devolve (payload, n_bits). O n_bits e indispensavel: o ultimo byte quase
    sempre sobra espaco e e preenchido com zeros; sem saber onde a mensagem
    termina, a decodificacao inventaria caracteres fantasmas no final.
    """
    bits = "".join(codigos[b] for b in dados)
    n_bits = len(bits)
    completo = bits + "0" * (-n_bits % 8)
    payload = bytes(int(completo[i:i + 8], 2) for i in range(0, len(completo), 8))
    return payload, n_bits


def decodificar(payload: bytes, n_bits: int, raiz: No) -> bytes:
    """
    Caminha a arvore bit a bit: 0 desce a esquerda, 1 desce a direita.
    Ao chegar numa folha, emite o byte e volta para a raiz.
    """
    saida = bytearray()
    no = raiz
    lidos = 0

    for byte in payload:
        for deslocamento in range(7, -1, -1):
            if lidos >= n_bits:
                return bytes(saida)
            bit = (byte >> deslocamento) & 1
            lidos += 1
            no = no.direita if bit else no.esquerda
            if no is None:
                raise ValueError("Bitstream incompatível com a árvore reconstruída.")
            if no.eh_folha:
                saida.append(no.simbolo)
                no = raiz

    return bytes(saida)


def arvore_para_dicionario(no: No) -> dict:
    """
    Converte a arvore em dicionario aninhado, para que a interface web possa
    desenha-la. Simbolos nao imprimiveis viram notacao hexadecimal.
    """
    if no is None:
        return None
    if no.eh_folha:
        caractere = chr(no.simbolo)
        if caractere == " ":
            visivel = "espaco"
        elif caractere == "\n":
            visivel = "\\n"
        elif caractere.isprintable():
            visivel = caractere
        else:
            visivel = f"\\x{no.simbolo:02x}"
        return {"folha": True, "simbolo": visivel, "frequencia": no.frequencia}
    return {
        "folha": False,
        "frequencia": no.frequencia,
        "esquerda": arvore_para_dicionario(no.esquerda),
        "direita": arvore_para_dicionario(no.direita),
    }


def desenhar_arvore(no: No, prefixo: str = "", rotulo: str = "raiz") -> str:
    """Desenho em texto da arvore, para conferir na apresentacao."""
    if no is None:
        return ""
    if no.eh_folha:
        simbolo = chr(no.simbolo)
        visivel = simbolo if simbolo.isprintable() else f"\\x{no.simbolo:02x}"
        return f"{prefixo}{rotulo}: '{visivel}' (freq {no.frequencia})\n"
    texto = f"{prefixo}{rotulo}: [{no.frequencia}]\n"
    texto += desenhar_arvore(no.esquerda, prefixo + "   ", "0 esq")
    texto += desenhar_arvore(no.direita, prefixo + "   ", "1 dir")
    return texto
