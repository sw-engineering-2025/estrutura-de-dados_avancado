#!/usr/bin/env python3
"""
Servidor web do MSGX -- interface grafica sobre o MESMO nucleo usado pela CLI.

Nenhuma logica de Huffman ou de cifra vive aqui: este arquivo so traduz
HTTP para chamadas de huffman.py / cifra.py / formato.py / ia.py. A CLI
(app.py) continua funcionando sem alteracao -- sao dois frontends para o
mesmo backend.

Execucao:
    python3 web.py            # http://localhost:8000
    python3 web.py 8001       # outra porta

Demonstracao com duas filiais ao mesmo tempo:

    # terminal 1 -- Marica
    MSGX_CHAVE="chave-combinada" python3 web.py 8000

    # terminal 2 -- Niteroi (mesma chave: consegue abrir)
    MSGX_CHAVE="chave-combinada" MSGX_PENDRIVE=./pendrive python3 web.py 8001

    # terminal 3 -- invasor (chave diferente: nao abre)
    MSGX_CHAVE="chave-errada" python3 web.py 8002

Sem dependencias externas: tudo com a biblioteca padrao do Python.
"""

import base64
import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cifra
import config
import formato
import historico
import huffman
import ia

RAIZ = Path(__file__).resolve().parent

# Layout normal: os arquivos da interface ficam em static/. Se alguem baixar
# tudo numa pasta so, eles ficam ao lado do web.py -- os dois casos funcionam.
ESTATICOS = RAIZ / "static" if (RAIZ / "static" / "index.html").is_file() else RAIZ

TIPOS_MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}


class Servidor(BaseHTTPRequestHandler):
    server_version = "MSGX"

    # ------------------------------------------------------------------
    # Utilitarios de resposta
    # ------------------------------------------------------------------

    def responder_json(self, dados, status=200):
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def responder_erro(self, mensagem, status=400):
        self.responder_json({"erro": mensagem}, status)

    def responder_arquivo(self, caminho: Path):
        if not caminho.is_file():
            self.responder_erro("Arquivo não encontrado.", 404)
            return
        corpo = caminho.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", TIPOS_MIME.get(caminho.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def ler_corpo(self) -> dict:
        tamanho = int(self.headers.get("Content-Length") or 0)
        if not tamanho:
            return {}
        return json.loads(self.rfile.read(tamanho).decode("utf-8"))

    def log_message(self, formato_texto, *args):
        print(f"  {self.command} {self.path}")

    # ------------------------------------------------------------------
    # Rotas
    # ------------------------------------------------------------------

    def servir_estatico(self, caminho: str) -> bool:
        """
        Entrega um arquivo da interface. Aceita tanto /static/estilo.css quanto
        /estilo.css, porque o projeto roda com os arquivos em static/ ou todos
        numa pasta so. Só tipos da interface passam -- .py nunca é servido.
        """
        nome = Path(caminho).name
        if not nome:
            return False

        alvo = ESTATICOS / nome
        if alvo.suffix not in TIPOS_MIME or not alvo.is_file():
            return False

        self.responder_arquivo(alvo)
        return True

    def do_GET(self):
        caminho = self.path.split("?")[0]

        try:
            if caminho == "/":
                self.responder_arquivo(ESTATICOS / "index.html")
            elif caminho == "/favicon.ico":
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
            elif caminho == "/api/configuracao":
                self.responder_json({
                    "filiais": {str(c): n for c, n in config.FILIAIS.items()},
                    "lacre": cifra.impressao_digital(config.CHAVE),
                    "limite": config.LIMITE_MENSAGEM_CURTA,
                    "pendrive": str(config.PENDRIVE),
                })
            elif caminho == "/api/pendrive":
                pasta = config.garantir_pendrive()
                arquivos = sorted(pasta.glob(f"*{config.EXTENSAO}"), reverse=True)
                self.responder_json({"arquivos": [
                    {"nome": a.name, "bytes": a.stat().st_size} for a in arquivos
                ]})
            elif caminho == "/api/historico":
                self.responder_json({"mensagens": [
                    {
                        "msg_id": m["msg_id"],
                        "direcao": m["direcao"],
                        "origem": config.nome_filial(m["origem"]),
                        "destino": config.nome_filial(m["destino"]),
                        "data": datetime.fromtimestamp(m["criada_em"], timezone.utc)
                                        .strftime("%d/%m/%Y %H:%M UTC"),
                        "bytes": m["bytes"],
                    }
                    for m in historico.listar()
                ]})
            elif not caminho.startswith("/api/") and self.servir_estatico(caminho):
                pass
            else:
                self.responder_erro("Rota não encontrada.", 404)
        except Exception as erro:
            # Nunca fechar a conexao sem corpo: resposta vazia vira um erro
            # incompreensivel do lado do navegador.
            self.responder_erro(f"Falha inesperada: {erro}", 500)

    def do_POST(self):
        try:
            corpo = self.ler_corpo()
        except (ValueError, UnicodeDecodeError):
            self.responder_erro("Corpo da requisição inválido.")
            return

        rotas = {
            "/api/ia": self.rota_ia,
            "/api/despachar": self.rota_despachar,
            "/api/receber": self.rota_receber,
            "/api/periciar": self.rota_periciar,
        }
        rota = rotas.get(self.path.split("?")[0])
        if rota is None:
            self.responder_erro("Rota não encontrada.", 404)
            return

        try:
            rota(corpo)
        except ValueError as erro:
            self.responder_erro(str(erro))
        except Exception as erro:                      # rede/IA/IO
            self.responder_erro(f"Falha inesperada: {erro}", 500)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def rota_ia(self, corpo):
        texto = (corpo.get("texto") or "").strip()
        if not texto:
            raise ValueError("Escreva alguma coisa antes de acionar a IA.")

        if corpo.get("acao") == "redigir":
            resultado, provedor = ia.redigir(texto, config.LIMITE_MENSAGEM_CURTA)
        else:
            resultado, provedor = ia.resumir(texto, config.LIMITE_MENSAGEM_CURTA)

        self.responder_json({
            "texto": resultado,
            "provedor": provedor,
            "antes": len(texto),
            "depois": len(resultado),
        })

    def rota_despachar(self, corpo):
        texto = (corpo.get("texto") or "").strip()
        if not texto:
            raise ValueError("A mensagem está vazia.")

        origem = int(corpo.get("origem", 1))
        destino = int(corpo.get("destino", 2))
        if origem == destino:
            raise ValueError("Origem e destino são a mesma filial.")

        pacote = formato.empacotar(texto, config.CHAVE, origem, destino)

        pasta = config.garantir_pendrive()
        nome = f"{pacote['msg_id']}{config.EXTENSAO}"
        (pasta / nome).write_bytes(pacote["arquivo"])
        historico.registrar(historico.ENVIADA, pacote["arquivo"])

        bits_originais = pacote["bits_originais"]
        bits_comprimidos = pacote["bits_comprimidos"]

        self.responder_json({
            "msg_id": str(pacote["msg_id"]),
            "nome_arquivo": nome,
            "arquivo": base64.b64encode(pacote["arquivo"]).decode("ascii"),
            "bits_originais": bits_originais,
            "bits_comprimidos": bits_comprimidos,
            "reducao": round(100 * (1 - bits_comprimidos / bits_originais), 1),
            "tamanho_arquivo": pacote["tamanho_arquivo"],
            "simbolos": len(pacote["frequencias"]),
            "lacre": cifra.impressao_digital(config.CHAVE),
            "arvore": huffman.arvore_para_dicionario(pacote["raiz"]),
            "codigos": self.tabela(pacote["codigos"], pacote["frequencias"]),
        })

    def rota_receber(self, corpo):
        arquivo = self.obter_arquivo(corpo)
        resultado = formato.desempacotar(arquivo, config.CHAVE)

        # So entra no historico o que abriu com a chave certa. Reabrir um item
        # do proprio historico nao gera registro novo -- senao uma mensagem
        # enviada, ao ser relida, apareceria tambem como "recebida".
        if not corpo.get("historico"):
            historico.registrar(historico.RECEBIDA, arquivo)

        self.responder_json({
            "texto": resultado["texto"],
            "origem": config.nome_filial(resultado["origem"]),
            "destino": config.nome_filial(resultado["destino"]),
            "msg_id": str(resultado["msg_id"]),
            "timestamp": resultado["timestamp"].strftime("%d/%m/%Y %H:%M:%S UTC"),
            "n_bits": resultado["n_bits"],
            "simbolos": len(resultado["frequencias"]),
            "lacre": cifra.impressao_digital(config.CHAVE),
            "arvore": huffman.arvore_para_dicionario(resultado["raiz"]),
            "codigos": self.tabela(resultado["codigos"], resultado["frequencias"]),
        })

    def rota_periciar(self, corpo):
        arquivo = self.obter_arquivo(corpo)
        envelope = formato.ler_envelope(arquivo)
        bloco = envelope["bloco_cifrado"]

        self.responder_json({
            "origem": config.nome_filial(envelope["origem"]),
            "destino": config.nome_filial(envelope["destino"]),
            "msg_id": str(envelope["msg_id"]),
            "timestamp": envelope["timestamp"].strftime("%d/%m/%Y %H:%M UTC"),
            "versao": envelope["versao"],
            "tamanho_bloco": envelope["tamanho_bloco"],
            "hex": " ".join(f"{b:02x}" for b in bloco[:128]),
            "truncado": len(bloco) > 128,
        })

    # ------------------------------------------------------------------

    def obter_arquivo(self, corpo) -> bytes:
        """
        Aceita o arquivo enviado pelo navegador, escolhido no pen drive ou
        guardado no historico local.
        """
        if corpo.get("historico"):
            arquivo = historico.obter_arquivo(str(corpo["historico"]),
                                              str(corpo.get("direcao", "")))
            if arquivo is None:
                raise ValueError("Mensagem não encontrada no histórico.")
            return arquivo

        if corpo.get("arquivo"):
            try:
                return base64.b64decode(corpo["arquivo"])
            except (ValueError, TypeError):
                raise ValueError("Arquivo enviado está corrompido.")

        nome = corpo.get("nome")
        if not nome:
            raise ValueError("Nenhum arquivo selecionado.")

        caminho = config.garantir_pendrive() / Path(nome).name
        if not caminho.is_file():
            raise ValueError("Arquivo não está mais no pen drive.")
        return caminho.read_bytes()

    @staticmethod
    def tabela(codigos, frequencias):
        linhas = []
        for simbolo in sorted(codigos, key=lambda s: (len(codigos[s]), s)):
            caractere = chr(simbolo)
            if caractere == " ":
                visivel = "espaco"
            elif caractere.isprintable():
                visivel = caractere
            else:
                visivel = f"\\x{simbolo:02x}"
            linhas.append({
                "simbolo": visivel,
                "frequencia": frequencias[simbolo],
                "codigo": codigos[simbolo],
            })
        return linhas


def main():
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

    faltando = [n for n in ("index.html", "estilo.css", "app.js")
                if not (ESTATICOS / n).is_file()]
    if faltando:
        print()
        print("  Interface incompleta. Nao encontrei em", ESTATICOS)
        for nome in faltando:
            print(f"    - {nome}")
        print("  Coloque os tres arquivos numa pasta 'static' ao lado do web.py")
        print("  (ou na mesma pasta dele) e rode de novo.")
        print()
        sys.exit(1)

    try:
        servidor = ThreadingHTTPServer(("127.0.0.1", porta), Servidor)
    except OSError:
        print(f"\n  A porta {porta} ja esta em uso.")
        print(f"  Encerre o outro servidor ou rode:  python3 web.py {porta + 1}\n")
        sys.exit(1)

    print()
    print(f"  MSGX no ar em http://localhost:{porta}")
    print("  Abra esse endereco no navegador -- nao abra o index.html direto")
    print("  nem pelo Live Server, senao as rotas /api nao existem.")
    print()
    print(f"  Filiais ..... {' | '.join(config.FILIAIS.values())}")
    print(f"  Lacre ....... {cifra.impressao_digital(config.CHAVE)}")
    print(f"  Pen drive ... {config.PENDRIVE}/")
    print(f"  Histórico ... {config.HISTORICO}")
    print("  Ctrl+C para encerrar.")
    print()

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\n  Encerrado.")
        servidor.server_close()


if __name__ == "__main__":
    main()
