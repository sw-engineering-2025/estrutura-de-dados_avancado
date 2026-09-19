"""
Camada de IA -- compressao SEMANTICA, antes da compressao ESTATISTICA.

A ideia que amarra o requisito "mensagens curtas": o usuario escreve do jeito
que pensa, a IA reduz o texto ao essencial, e so entao a arvore de Huffman
comprime o que sobrou. Sao duas compressoes de naturezas diferentes:

    IA      -> descarta SIGNIFICADO redundante (com perda)
    Huffman -> descarta BITS redundantes       (sem perda)

Se houver chave de API no ambiente, usa o provedor. Se nao houver -- ou se a
rede cair no meio da apresentacao -- cai para um resumo extrativo local, que
sempre funciona e e deterministico. Nenhuma das duas rotas toca no texto ja
cifrado: a IA age antes da arvore, sobre texto claro, dentro da filial.
"""

import json
import os
import re
import urllib.error
import urllib.request

TEMPO_LIMITE = 20


# ----------------------------------------------------------------------
# Fallback local (sempre disponivel)
# ----------------------------------------------------------------------

_VAZIAS = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "no", "na",
    "nos", "nas", "um", "uma", "que", "para", "por", "com", "se", "ao", "aos",
    "ja", "mas", "sobre", "como", "foi", "ser", "esta", "isso", "muito",
}


def _resumo_extrativo(texto: str, limite: int) -> str:
    """
    Pontua cada frase pela frequencia das palavras relevantes que contem e
    mantem as melhores, na ordem original, ate atingir o limite.
    """
    texto = " ".join(texto.split())
    if len(texto) <= limite:
        return texto

    frases = [f.strip() for f in re.split(r"(?<=[.!?;])\s+", texto) if f.strip()]
    if len(frases) <= 1:
        return texto[:limite].rsplit(" ", 1)[0] + "..."

    contagem = {}
    for palavra in re.findall(r"\w+", texto.lower()):
        if palavra not in _VAZIAS and len(palavra) > 2:
            contagem[palavra] = contagem.get(palavra, 0) + 1

    pontuadas = []
    for indice, frase in enumerate(frases):
        palavras = [
            p for p in re.findall(r"\w+", frase.lower())
            if p not in _VAZIAS and len(p) > 2
        ]
        nota = sum(contagem.get(p, 0) for p in palavras) / (len(palavras) or 1)
        if re.search(r"\d", frase):
            nota *= 1.6          # numeros, SKU, datas e horarios sao o que importa
        if len(palavras) < 4:
            nota *= 0.3          # "qualquer coisa me chama" nao merece o espaco
        pontuadas.append((nota, indice, frase))

    escolhidas, total = [], 0
    for _, indice, frase in sorted(pontuadas, key=lambda t: -t[0]):
        if total + len(frase) + 1 > limite:
            continue
        escolhidas.append((indice, frase))
        total += len(frase) + 1
    if not escolhidas:
        return texto[:limite].rsplit(" ", 1)[0] + "..."

    return " ".join(frase for _, frase in sorted(escolhidas))


# ----------------------------------------------------------------------
# Provedores remotos
# ----------------------------------------------------------------------

def _chamar_anthropic(instrucao: str, chave_api: str) -> str:
    corpo = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 400,
        "messages": [{"role": "user", "content": instrucao}],
    }).encode("utf-8")
    requisicao = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=corpo,
        headers={
            "content-type": "application/json",
            "x-api-key": chave_api,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(requisicao, timeout=TEMPO_LIMITE) as resposta:
        dados = json.loads(resposta.read())
    return "".join(b.get("text", "") for b in dados.get("content", [])).strip()


def _chamar_gemini(instrucao: str, chave_api: str) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={chave_api}"
    )
    corpo = json.dumps({
        "contents": [{"parts": [{"text": instrucao}]}]
    }).encode("utf-8")
    requisicao = urllib.request.Request(
        url, data=corpo, headers={"content-type": "application/json"}
    )
    with urllib.request.urlopen(requisicao, timeout=TEMPO_LIMITE) as resposta:
        dados = json.loads(resposta.read())
    partes = dados["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in partes).strip()


def _gerar(instrucao: str):
    """Tenta os provedores disponiveis. Devolve (texto, nome_do_provedor)."""
    chave = os.environ.get("ANTHROPIC_API_KEY")
    if chave:
        try:
            return _chamar_anthropic(instrucao, chave), "Claude"
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError):
            pass

    chave = os.environ.get("GEMINI_API_KEY")
    if chave:
        try:
            return _chamar_gemini(instrucao, chave), "Gemini"
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError):
            pass

    return None, None


# ----------------------------------------------------------------------
# API usada pelo aplicativo
# ----------------------------------------------------------------------

def resumir(texto: str, limite: int):
    """Reduz o texto ao essencial. Devolve (texto_resumido, provedor_usado)."""
    instrucao = (
        "Resuma a mensagem abaixo em no maximo "
        f"{limite} caracteres, mantendo nomes, numeros, datas e a acao pedida. "
        "Responda apenas com o texto resumido, em portugues, sem comentarios.\n\n"
        f"Mensagem:\n{texto}"
    )
    resultado, provedor = _gerar(instrucao)
    if resultado:
        return " ".join(resultado.split())[:limite * 2], provedor
    return _resumo_extrativo(texto, limite), "local (extrativo)"


def redigir(intencao: str, limite: int):
    """Escreve uma mensagem curta e objetiva a partir de uma intencao."""
    instrucao = (
        "Escreva uma mensagem corporativa curta, direta e educada, com no maximo "
        f"{limite} caracteres, em portugues do Brasil, a partir da intencao abaixo. "
        "Responda apenas com a mensagem.\n\n"
        f"Intencao: {intencao}"
    )
    resultado, provedor = _gerar(instrucao)
    if resultado:
        return " ".join(resultado.split())[:limite * 2], provedor

    intencao = " ".join(intencao.split())
    rascunho = f"Prezados, {intencao[0].lower() + intencao[1:]}. Fico no aguardo. Att."
    return _resumo_extrativo(rascunho, limite), "local (modelo de texto)"
