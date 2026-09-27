#!/usr/bin/env python3
"""Testes do pipeline. Executar: python3 testes.py"""

import tempfile
from pathlib import Path

import config
import formato
import historico
import huffman

CHAVE = "chave-de-teste-123"
OUTRA = "chave-errada-456"

CASOS = [
    "Reposicao urgente: enviar 40 pecas da colecao verao para Niteroi ate sexta.",
    "aaaaaaaaaa",
    "a",
    "Acentuacao: coracao, ate amanha, R$ 1.250,00 -- confirmacao pendente!",
    "0123456789" * 20,
    "Estoque da loja Marica zerou no SKU 88213. Motoboy sai as 14h.",
]

falhas = 0


def verificar(condicao, descricao):
    global falhas
    if condicao:
        print(f"  ok   {descricao}")
    else:
        falhas += 1
        print(f"  FALHA{descricao}")


print("1. Ida e volta completa (origem -> pen drive -> destino)")
for texto in CASOS:
    pacote = formato.empacotar(texto, CHAVE, 1, 2)
    lido = formato.desempacotar(pacote["arquivo"], CHAVE)
    verificar(lido["texto"] == texto, f"texto preservado ({len(texto)} chars)")

print("\n2. Arvore reconstruida e identica a original")
for texto in CASOS:
    pacote = formato.empacotar(texto, CHAVE, 1, 2)
    lido = formato.desempacotar(pacote["arquivo"], CHAVE)
    verificar(pacote["codigos"] == lido["codigos"], f"tabela de codigos bate ({len(texto)} chars)")

print("\n3. Codigos de prefixo (nenhum codigo e prefixo de outro)")
for texto in CASOS:
    codigos = list(formato.empacotar(texto, CHAVE, 1, 2)["codigos"].values())
    prefixo = any(
        a != b and b.startswith(a)
        for i, a in enumerate(codigos)
        for b in codigos[i + 1:] + codigos[:i]
    )
    verificar(not prefixo, f"propriedade de prefixo mantida ({len(codigos)} simbolos)")

print("\n4. Chave errada nao abre a mensagem")
pacote = formato.empacotar(CASOS[0], CHAVE, 1, 2)
try:
    formato.desempacotar(pacote["arquivo"], OUTRA)
    verificar(False, "deveria ter recusado a chave errada")
except ValueError:
    verificar(True, "chave errada recusada")

print("\n5. Arquivo corrompido e detectado pelo CRC")
adulterado = bytearray(pacote["arquivo"])
adulterado[40] ^= 0xFF
try:
    formato.desempacotar(bytes(adulterado), CHAVE)
    verificar(False, "deveria ter detectado a corrupcao")
except ValueError:
    verificar(True, "corrupcao detectada")

print("\n6. Envelope e legivel sem a chave; conteudo nao")
envelope = formato.ler_envelope(pacote["arquivo"])
verificar(envelope["origem"] == 1 and envelope["destino"] == 2, "roteamento visivel")
verificar(CASOS[0].encode() not in pacote["arquivo"], "texto nao aparece em claro no arquivo")

print("\n7. Mesma mensagem gera arquivos diferentes (nonce por mensagem)")
a = formato.empacotar(CASOS[0], CHAVE, 1, 2)["arquivo"]
b = formato.empacotar(CASOS[0], CHAVE, 1, 2)["arquivo"]
verificar(a != b, "keystream nao se repete entre mensagens")

print("\n8. Desempate deterministico do heap")
freq = {ord("a"): 1, ord("b"): 1, ord("c"): 1, ord("d"): 1, ord("e"): 1}
c1 = huffman.gerar_codigos(huffman.construir_arvore(freq))
c2 = huffman.gerar_codigos(huffman.construir_arvore(dict(reversed(list(freq.items())))))
verificar(c1 == c2, "frequencias iguais produzem sempre a mesma arvore")

print("\n9. Historico SQLite guarda a mensagem cifrada")
with tempfile.TemporaryDirectory() as pasta:
    config.HISTORICO = Path(pasta) / "historico.db"      # nunca suja o banco real

    pacote = formato.empacotar(CASOS[0], CHAVE, 1, 2)
    msg_id = str(pacote["msg_id"])
    historico.registrar(historico.ENVIADA, pacote["arquivo"])
    historico.registrar(historico.ENVIADA, pacote["arquivo"])      # repetido
    historico.registrar(historico.RECEBIDA, pacote["arquivo"])

    registros = historico.listar()
    verificar(len(registros) == 2, "registro repetido nao duplica; enviada e recebida coexistem")
    verificar(registros[0]["origem"] == 1 and registros[0]["destino"] == 2,
              "envelope listado sem precisar da chave")

    guardado = historico.obter_arquivo(msg_id, historico.ENVIADA)
    verificar(formato.desempacotar(guardado, CHAVE)["texto"] == CASOS[0],
              "mensagem reaberta do historico com a chave")
    try:
        formato.desempacotar(guardado, OUTRA)
        verificar(False, "historico deveria exigir a chave certa")
    except ValueError:
        verificar(True, "historico com chave errada recusado")

    verificar(CASOS[0].encode() not in config.HISTORICO.read_bytes(),
              "texto nao aparece em claro no historico.db")
    verificar(historico.obter_arquivo("inexistente", historico.ENVIADA) is None,
              "id desconhecido devolve None")

print("\n" + ("-" * 50))
print("TODOS OS TESTES PASSARAM" if falhas == 0 else f"{falhas} FALHA(S)")
