# MSGX — Mensageria assíncrona entre filiais

**Disciplina:** Estrutura de Dados Avançada — Engenharia de Software, 4º período
**Entrega:** protótipo de 1 sprint

---

## 1. O problema

Duas filiais (**Maricá** e **Niterói**) precisam trocar mensagens operacionais.
Após um incidente de **vazamento de dados**, a comunicação pela rede foi
suspensa: as mensagens passam a ser gravadas em pen drive e levadas
fisicamente por motoboy entre as unidades.

O pen drive pode ser perdido, roubado ou copiado no caminho. Isso define o
requisito central do sistema:

> O arquivo, sozinho, não pode ser suficiente para ler a mensagem.

A chave é combinada previamente entre as duas filiais e **nunca viaja no pen
drive** — só o conteúdo cifrado viaja.

---

## 2. Como rodar

O projeto tem **duas interfaces sobre o mesmo núcleo**: linha de comando e web.
Nenhuma lógica de Huffman ou de cifra é duplicada — `web.py` e `app.py` apenas
chamam `huffman.py`, `cifra.py`, `formato.py` e `ia.py`.

### Interface web

```bash
cd msgx
python3 web.py            # abra http://localhost:8000
```

Sem dependências: o servidor usa apenas a biblioteca padrão do Python, então
não há `pip install` para dar errado na hora da apresentação.

Três telas:

- **Despachar** — escrever (ou pedir à IA para resumir/redigir), lacrar, ver a
  árvore desenhada e baixar o `.msgx`.
- **Receber** — abrir uma remessa do pen drive ou de um arquivo enviado, com a
  árvore reconstruída ao lado do texto recuperado.
- **Perícia** — o que um terceiro leria no arquivo sem ter a chave.

### Interface de linha de comando

```bash
python3 app.py
```

### Testes automatizados

```bash
python3 testes.py
```

### Roteiro de demonstração com duas filiais

Dois terminais, duas portas, a mesma chave — as duas filiais conversando:

```bash
# terminal 1 — Maricá
MSGX_CHAVE="chave-combinada" python3 web.py 8000

# terminal 2 — Niterói
MSGX_CHAVE="chave-combinada" python3 web.py 8001

# terminal 3 — o pen drive que caiu na estrada
MSGX_CHAVE="chave-errada" python3 web.py 8002
```

Em `:8000`, escolha *Maricá*, escreva a mensagem e lacre. Em `:8001`, escolha
*Niterói* e abra a remessa — o texto aparece. Em `:8002`, a mesma remessa é
recusada, e a aba **Perícia** mostra exatamente o que ainda assim vaza. Repare
que o campo *chave desta filial* no topo exibe impressões digitais diferentes
nas duas primeiras e na terceira.

Para separar de verdade as duas filiais (máquinas distintas), baixe o `.msgx`
pelo botão, leve no pen drive e use *Selecionar arquivo* na tela Receber.

### Simulando o trajeto pela CLI

O diretório `./pendrive/` representa o dispositivo. Rode `app.py`, escolha
**1** para gravar, copie a pasta para a outra máquina — esse é o motoboy — e
escolha **2** do outro lado para ler.

### Se a interface reclamar das rotas /api

A página precisa ser servida pelo próprio `web.py`. Abrir o `index.html` pelo
Live Server do VS Code, por `python3 -m http.server` ou com dois cliques no
arquivo faz o HTML e o CSS carregarem normalmente — mas nenhum desses serve as
rotas `/api`, e as chamadas voltam como página de erro HTML ou resposta vazia.
O sintoma é a interface aparecer bonita com o campo *chave desta filial* ainda
nos pontinhos.

Feche o outro servidor, rode `python3 web.py` na pasta do projeto e use o
endereço que ele imprimir no terminal.

### Variáveis de ambiente

| Variável | Função |
|---|---|
| `MSGX_CHAVE` | Chave pré-compartilhada entre as filiais |
| `MSGX_PENDRIVE` | Caminho do pen drive (ex.: `/media/usuario/PENDRIVE`) |
| `ANTHROPIC_API_KEY` ou `GEMINI_API_KEY` | Habilita a IA remota (opcional) |

Sem chave de API, a IA cai automaticamente para um resumidor extrativo local.
A demonstração nunca depende da internet da sala.

---

## 3. Arquitetura

| Módulo | Responsabilidade |
|---|---|
| `huffman.py` | Árvore binária, min-heap, geração de códigos, encode/decode |
| `cifra.py` | Keystream SHA-256, XOR, CRC32 |
| `formato.py` | Serialização e leitura do arquivo `.msgx` |
| `ia.py` | Resumo/redação da mensagem, com fallback offline |
| `config.py` | Filiais, chave, caminho do pen drive |
| `app.py` | Interface de linha de comando |
| `web.py` | Servidor HTTP que expõe o núcleo como API JSON |
| `static/` | Interface web (HTML, CSS e JavaScript) |
| `testes.py` | Suíte de verificação do pipeline |

As duas interfaces são intercambiáveis: uma mensagem lacrada na web abre na
CLI e vice-versa, porque ambas produzem o mesmo `.msgx` pelo mesmo código.

### API HTTP

| Rota | Função |
|---|---|
| `GET /api/configuracao` | Filiais, limite de caracteres e impressão digital da chave |
| `GET /api/pendrive` | Remessas presentes no pen drive |
| `POST /api/ia` | Resume ou redige a mensagem |
| `POST /api/despachar` | Comprime, cifra, grava e devolve o arquivo em base64 |
| `POST /api/receber` | Decifra, reconstrói a árvore e devolve o texto |
| `POST /api/periciar` | Devolve só o envelope e o dump hexadecimal do bloco cifrado |

### Pipeline

**Origem**

```
texto → [IA: resumo semântico] → bytes UTF-8 → frequências
      → árvore de Huffman → tabela de códigos → bitstream
      → cifra XOR (chave + nonce) → arquivo .msgx → pen drive
```

**Destino**

```
arquivo .msgx → valida CRC → decifra com a chave
              → lê tabela de frequências → REFAZ A ÁRVORE
              → percorre o bitstream bit a bit → texto original
```

São **duas compressões de naturezas diferentes**: a IA descarta significado
redundante (com perda), o Huffman descarta bits redundantes (sem perda).

---

## 4. Formato dos dados (`.msgx`)

Binário, big-endian.

```
[ EM CLARO — o "envelope" ]
MAGIC       4 bytes    "MSGX"
VERSAO      1 byte     0x01
ORIGEM      1 byte     0x01 = Maricá, 0x02 = Niterói
DESTINO     1 byte
MSG_ID     16 bytes    UUID4 — também é o nonce da cifra
TIMESTAMP   8 bytes    uint64, epoch em segundos
TAM_BLOCO   4 bytes    uint32

[ CIFRADO COM A CHAVE PRÉ-COMPARTILHADA ]
N_SIMB      1 byte     nº de símbolos distintos, gravado como n-1 (1..256)
TABELA      n × 3      símbolo (1 byte) + frequência (2 bytes, uint16)
N_BITS      4 bytes    uint32, bits úteis do payload
PAYLOAD     ⌈N_BITS/8⌉ bitstream da árvore de Huffman

[ EM CLARO ]
CRC32       4 bytes    sobre todos os bytes anteriores
```

Cabeçalho fixo: 35 bytes. Rodapé: 4 bytes.

---

## 5. Decisões de projeto que valem defender

**Huffman sobre bytes UTF-8, não sobre caracteres.**
Acento, cedilha e emoji funcionam sem nenhum tratamento especial, e o alfabeto
fica sempre contido em 0–255, o que permite 1 byte por símbolo na tabela.

**Desempate determinístico no min-heap.**
Este é o ponto que quebra implementações ingênuas. Para a árvore reconstruída
no destino ser idêntica à da origem, dois nós de mesma frequência precisam sair
do heap sempre na mesma ordem. Resolvido com a tupla
`(frequência, ordem_de_inserção, nó)` e com as folhas entrando em ordem
crescente de símbolo. Sem isso, as árvores divergem e a leitura devolve lixo.
O teste nº 8 cobre exatamente esse caso.

**`N_BITS` explícito.**
O último byte quase sempre sobra espaço e é preenchido com zeros. Sem saber
onde a mensagem termina, o decodificador continuaria caminhando na árvore e
inventaria caracteres fantasmas no final.

**Tabela de frequências dentro da parte cifrada.**
Se viajasse em claro, quem achasse o pen drive já teria o alfabeto usado e o
tamanho real da mensagem, mesmo sem ler o texto. Em claro fica só o roteamento
— o equivalente ao envelope de uma carta.

**Nonce por mensagem (o `MSG_ID`).**
Um keystream XOR reutilizado é o clássico *two-time pad*: o XOR de duas
mensagens cifradas com o mesmo keystream elimina a chave da equação. Derivando
o keystream de `SHA256(chave ‖ msg_id ‖ contador)`, duas mensagens idênticas
geram arquivos completamente diferentes. O teste nº 7 comprova.

**CRC32.**
Pen drive cai no chão e setor corrompe. O checksum distingue "arquivo
corrompido no transporte" de "chave errada" — diagnósticos diferentes, ações
diferentes.

---

## 6. Complexidade

Sendo `n` o tamanho da mensagem em bytes e `k` o número de símbolos distintos
(`k ≤ 256`):

| Etapa | Custo |
|---|---|
| Contagem de frequências | O(n) |
| Construção da árvore | O(k log k) |
| Geração da tabela de códigos | O(k) |
| Codificação | O(n) |
| Cifra XOR | O(n) |
| Decodificação (bit a bit) | O(B), B = bits do payload |

Total: **O(n + k log k)**. Como `k` é limitado a 256, na prática o
comportamento é linear no tamanho da mensagem.

---

## 7. Backlog da sprint

| ID | História de usuário | Critérios de aceitação |
|---|---|---|
| H1 | Como **operador da filial**, eu quero escrever uma mensagem e gravá-la no pen drive, para que ela seja levada em segurança pelo motoboy | O arquivo `.msgx` é criado; o texto não aparece em claro no arquivo |
| H2 | Como **operador da filial de destino**, eu quero abrir o arquivo do pen drive, para que eu leia a mensagem enviada | A árvore é reconstruída e o texto recuperado é idêntico ao original |
| H3 | Como **gestor**, eu quero que a mensagem seja ilegível sem a chave, para que um pen drive perdido não gere novo vazamento | Com chave divergente, o sistema recusa a leitura com mensagem clara |
| H4 | Como **operador**, eu quero que a IA resuma meu texto, para que a mensagem caiba no formato curto | Texto longo é reduzido; o sistema funciona mesmo sem internet |
| H5 | Como **auditor**, eu quero inspecionar o que o arquivo revela sem a chave, para que eu avalie o risco residual | A tela de auditoria exibe apenas envelope e bytes cifrados |
| H6 | Como **operador**, eu quero ser avisado se o arquivo chegou corrompido, para que eu não confunda defeito com invasão | Alteração de 1 byte é detectada pelo CRC |

Fora do escopo desta sprint: interface gráfica, múltiplas filiais, fila de
mensagens, confirmação de entrega, rotação automática de chaves.

---

## 8. Limitações honestas

- **Mensagens curtas pagam o cabeçalho.** Em textos de ~60 caracteres, o
  arquivo final é maior que o texto original: o cabeçalho de 35 bytes mais a
  tabela de frequências superam o ganho da compressão. Aqui a árvore está
  presente pela estrutura de dados e pelo sigilo, não pela economia de espaço.
  O ganho do Huffman aparece a partir de algumas centenas de bytes.
- **XOR com keystream não é AES.** A construção é correta em princípio (stream
  cipher com nonce), mas não passou por análise criptográfica nem tem
  autenticação — um atacante pode alterar bits do texto cifrado, e o CRC não
  impede isso porque também é recalculável. Um sistema real usaria AES-GCM ou
  ChaCha20-Poly1305.
- **A chave é estática.** Não há rotação nem distribuição segura — ela é
  combinada presencialmente entre as filiais.
- **A IA trabalha sobre texto em claro**, dentro da filial, antes da cifra. Se o
  provedor for remoto, o texto original trafega até a API — em produção isso
  exigiria modelo local ou acordo de tratamento de dados.

### Evoluções naturais

- **Huffman canônico**: armazenar apenas o comprimento de cada código (1 byte
  por símbolo) em vez da tabela de frequências. Cabeçalho menor e determinismo
  garantido por construção.
- Autenticação com HMAC no lugar do CRC.
- Fila de mensagens e confirmação de entrega no retorno do motoboy.



