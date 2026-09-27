#!/usr/bin/env python3
"""
MSGX -- mensageria assincrona entre as filiais Marica e Niteroi.

Execucao:
    python3 app.py

Simulacao do trajeto: a filial de origem grava o .msgx na pasta ./pendrive,
o "motoboy" leva a pasta (ou o pen drive de verdade) ate a outra filial, e la
o mesmo programa, configurado com a outra filial, abre o arquivo.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import cifra
import config
import formato
import historico
import huffman
import ia

LARGURA = 66


def titulo(texto):
    print("\n" + "=" * LARGURA)
    print(f" {texto}")
    print("=" * LARGURA)


def perguntar(rotulo, padrao=None):
    sufixo = f" [{padrao}]" if padrao else ""
    resposta = input(f"{rotulo}{sufixo}: ").strip()
    return resposta or (padrao or "")


def escolher_filial(rotulo):
    print(f"\n{rotulo}:")
    for codigo, nome in config.FILIAIS.items():
        print(f"  {codigo}) {nome}")
    while True:
        escolha = input("Opcao: ").strip()
        if escolha.isdigit() and int(escolha) in config.FILIAIS:
            return int(escolha)
        print("Filial invalida.")


# ----------------------------------------------------------------------

def escrever_mensagem():
    titulo("ESCREVER MENSAGEM")

    origem = escolher_filial("Filial de origem")
    destino = escolher_filial("Filial de destino")
    if origem == destino:
        print("\nOrigem e destino sao a mesma filial. Nao ha o que transportar.")
        return

    print("\nComo deseja compor a mensagem?")
    print("  1) Digitar a mensagem")
    print("  2) Digitar um texto longo e deixar a IA resumir")
    print("  3) Descrever a intencao e deixar a IA redigir")
    modo = input("Opcao [1]: ").strip() or "1"

    if modo == "2":
        bruto = perguntar("\nTexto completo")
        if not bruto:
            print("Nada a enviar.")
            return
        print("\nResumindo...")
        texto, provedor = ia.resumir(bruto, config.LIMITE_MENSAGEM_CURTA)
        print(f"IA ({provedor}): {len(bruto)} -> {len(texto)} caracteres")
        print(f"Mensagem: {texto}")
        if perguntar("Usar este texto? (s/n)", "s").lower() != "s":
            texto = perguntar("Digite a mensagem final")
    elif modo == "3":
        intencao = perguntar("\nO que voce precisa comunicar")
        if not intencao:
            print("Nada a enviar.")
            return
        print("\nRedigindo...")
        texto, provedor = ia.redigir(intencao, config.LIMITE_MENSAGEM_CURTA)
        print(f"IA ({provedor}): {texto}")
        if perguntar("Usar este texto? (s/n)", "s").lower() != "s":
            texto = perguntar("Digite a mensagem final")
    else:
        texto = perguntar("\nMensagem")

    if not texto:
        print("Nada a enviar.")
        return

    resultado = formato.empacotar(texto, config.CHAVE, origem, destino)

    pasta = config.garantir_pendrive()
    caminho = pasta / f"{resultado['msg_id']}{config.EXTENSAO}"
    caminho.write_bytes(resultado["arquivo"])
    historico.registrar(historico.ENVIADA, resultado["arquivo"])

    bits_originais = resultado["bits_originais"]
    bits_comprimidos = resultado["bits_comprimidos"]
    reducao = 100 * (1 - bits_comprimidos / bits_originais)

    titulo("MENSAGEM GRAVADA NO PEN DRIVE")
    print(f"Arquivo ......... {caminho}")
    print(f"Rota ............ {config.nome_filial(origem)} -> {config.nome_filial(destino)}")
    print(f"ID .............. {resultado['msg_id']}")
    print(f"Chave (digital) . {cifra.impressao_digital(config.CHAVE)}")
    print()
    print(f"Texto original .. {bits_originais} bits ({bits_originais // 8} bytes UTF-8)")
    print(f"Huffman ......... {bits_comprimidos} bits  ({reducao:.1f}% de reducao)")
    print(f"Arquivo final ... {resultado['tamanho_arquivo']} bytes (com cabecalho e tabela)")
    if resultado["tamanho_arquivo"] * 8 > bits_originais:
        print("  Observacao: em mensagens curtas o cabecalho pesa mais que o ganho")
        print("  da compressao. Aqui a arvore existe pelo sigilo, nao pelo tamanho.")

    if perguntar("\nVer a tabela de codigos e a arvore? (s/n)", "n").lower() == "s":
        mostrar_arvore(resultado["raiz"], resultado["codigos"], resultado["frequencias"])

    print("\nPen drive pronto. Pode entregar ao motoboy.")


def ler_mensagem():
    titulo("LER MENSAGEM DO PEN DRIVE")

    pasta = config.garantir_pendrive()
    arquivos = sorted(pasta.glob(f"*{config.EXTENSAO}"))
    if not arquivos:
        print(f"Nenhum arquivo {config.EXTENSAO} encontrado em {pasta}/")
        return

    for indice, arquivo in enumerate(arquivos, 1):
        print(f"  {indice}) {arquivo.name}  ({arquivo.stat().st_size} bytes)")
    escolha = input("\nArquivo: ").strip()
    if not (escolha.isdigit() and 1 <= int(escolha) <= len(arquivos)):
        print("Opcao invalida.")
        return
    caminho = arquivos[int(escolha) - 1]

    arquivo = caminho.read_bytes()
    try:
        resultado = formato.desempacotar(arquivo, config.CHAVE)
    except ValueError as erro:
        print(f"\nFalha na leitura: {erro}")
        return

    historico.registrar(historico.RECEBIDA, arquivo)
    exibir_mensagem(resultado)


def exibir_mensagem(resultado):
    titulo("MENSAGEM RECUPERADA")
    print(f"De .............. {config.nome_filial(resultado['origem'])}")
    print(f"Para ............ {config.nome_filial(resultado['destino'])}")
    print(f"Enviada em ...... {resultado['timestamp']:%d/%m/%Y %H:%M:%S} UTC")
    print(f"ID .............. {resultado['msg_id']}")
    print(f"Chave (digital) . {cifra.impressao_digital(config.CHAVE)}")
    print(f"\nTexto:\n  {resultado['texto']}")

    if perguntar("\nVer a arvore reconstruida? (s/n)", "n").lower() == "s":
        mostrar_arvore(resultado["raiz"], resultado["codigos"], resultado["frequencias"])


def ver_historico():
    titulo("HISTORICO DESTA FILIAL")

    mensagens = historico.listar()
    if not mensagens:
        print(f"Nenhuma mensagem registrada em {config.HISTORICO}")
        return

    for indice, m in enumerate(mensagens, 1):
        data = datetime.fromtimestamp(m["criada_em"], timezone.utc)
        rota = f"{config.nome_filial(m['origem'])} -> {config.nome_filial(m['destino'])}"
        print(f"  {indice:>2}) {data:%d/%m/%Y %H:%M}  {m['direcao']:<8}  {rota}  "
              f"[{m['msg_id'][:8]}]")

    escolha = input("\nAbrir qual (Enter para voltar): ").strip()
    if not escolha:
        return
    if not (escolha.isdigit() and 1 <= int(escolha) <= len(mensagens)):
        print("Opcao invalida.")
        return

    escolhida = mensagens[int(escolha) - 1]
    arquivo = historico.obter_arquivo(escolhida["msg_id"], escolhida["direcao"])
    try:
        # O historico guarda o .msgx cifrado: reabrir exige a chave, igual ao pen drive.
        exibir_mensagem(formato.desempacotar(arquivo, config.CHAVE))
    except ValueError as erro:
        print(f"\nFalha na leitura: {erro}")


def auditar():
    """Mostra o que um terceiro consegue extrair do pen drive perdido."""
    titulo("AUDITORIA -- O QUE VAZA SE O PEN DRIVE FOR PERDIDO")

    pasta = config.garantir_pendrive()
    arquivos = sorted(pasta.glob(f"*{config.EXTENSAO}"))
    if not arquivos:
        print(f"Nenhum arquivo {config.EXTENSAO} encontrado em {pasta}/")
        return

    for indice, arquivo in enumerate(arquivos, 1):
        print(f"  {indice}) {arquivo.name}")
    escolha = input("\nArquivo: ").strip()
    if not (escolha.isdigit() and 1 <= int(escolha) <= len(arquivos)):
        print("Opcao invalida.")
        return

    bruto = arquivos[int(escolha) - 1].read_bytes()
    envelope = formato.ler_envelope(bruto)

    print("\nVisivel sem a chave (o 'envelope'):")
    print(f"  origem ........ {config.nome_filial(envelope['origem'])}")
    print(f"  destino ....... {config.nome_filial(envelope['destino'])}")
    print(f"  data .......... {envelope['timestamp']:%d/%m/%Y %H:%M} UTC")
    print(f"  id ............ {envelope['msg_id']}")
    print(f"  bloco cifrado . {envelope['tamanho_bloco']} bytes")

    print("\nPrimeiros bytes do bloco cifrado:")
    print("  " + " ".join(f"{b:02x}" for b in envelope["bloco_cifrado"][:32]))

    print("\nIlegivel sem a chave: alfabeto usado, tabela de frequencias,")
    print("tamanho real da mensagem, formato da arvore e o texto.")
    print("A chave nunca viaja no pen drive -- ela ja esta nas duas filiais.")


def mostrar_arvore(raiz, codigos, frequencias):
    print("\nTabela de codigos:")
    for simbolo in sorted(codigos, key=lambda s: (len(codigos[s]), s)):
        caractere = chr(simbolo)
        visivel = repr(caractere) if caractere.isprintable() else f"\\x{simbolo:02x}"
        print(f"  {visivel:>6}  freq {frequencias[simbolo]:>3}  ->  {codigos[simbolo]}")
    print("\nArvore:")
    print(huffman.desenhar_arvore(raiz))


def menu():
    while True:
        titulo("MSGX -- MENSAGERIA ASSINCRONA ENTRE FILIAIS")
        print(f"Filiais: {' | '.join(config.FILIAIS.values())}")
        print(f"Pen drive: {config.PENDRIVE}/   Chave: {cifra.impressao_digital(config.CHAVE)}")
        print()
        print("  1) Escrever mensagem e gravar no pen drive")
        print("  2) Ler mensagem do pen drive")
        print("  3) Auditar arquivo (simular vazamento)")
        print("  4) Historico de mensagens desta filial")
        print("  0) Sair")

        opcao = input("\nOpcao: ").strip()
        if opcao == "1":
            escrever_mensagem()
        elif opcao == "2":
            ler_mensagem()
        elif opcao == "3":
            auditar()
        elif opcao == "4":
            ver_historico()
        elif opcao == "0":
            print("Ate mais.")
            return
        else:
            print("Opcao invalida.")


if __name__ == "__main__":
    try:
        menu()
    except (KeyboardInterrupt, EOFError):
        print("\nEncerrado.")
        sys.exit(0)
