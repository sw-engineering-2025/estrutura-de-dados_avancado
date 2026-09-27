/* ------------------------------------------------------------------
   MSGX — interface web. Toda a criptografia e a árvore vivem no Python;
   este arquivo só conversa com a API e desenha o resultado.
   ------------------------------------------------------------------ */

const PALETA = {          // espelha os tokens de estilo.css
  tinta: "#13202a",
  linha: "#7d9291",
  carimbo: "#a8352b",
  papel: "#f1f4f3",
};

const estado = {
  filialAtual: 1,
  filiais: {},
  limite: 180,
  pacote: null,
};

const $ = (seletor) => document.querySelector(seletor);
const $$ = (seletor) => document.querySelectorAll(seletor);

/* ----------------------------------------------------------- utilidades */

const SEM_SERVIDOR =
  "As rotas /api não responderam. Esta página precisa ser servida pelo próprio "
  + "web.py: feche o Live Server (ou o python3 -m http.server), rode "
  + "python3 web.py na pasta do projeto e abra o endereço que ele imprimir.";

async function chamar(rota, dados) {
  const opcoes = dados
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados) }
    : {};

  let resposta;
  try {
    resposta = await fetch(rota, opcoes);
  } catch {
    throw new Error("Servidor fora do ar. Confira se o web.py continua rodando no terminal.");
  }

  const bruto = await resposta.text();

  let corpo;
  try {
    corpo = JSON.parse(bruto);
  } catch {
    // Veio HTML (página de erro de outro servidor) ou corpo vazio.
    throw new Error(SEM_SERVIDOR);
  }

  if (!resposta.ok) throw new Error(corpo.erro || `O servidor respondeu ${resposta.status}.`);
  return corpo;
}

function mostrarErro(seletor, mensagem) {
  const campo = $(seletor);
  campo.textContent = mensagem;
  campo.hidden = !mensagem;
}

function paraBase64(buffer) {
  let binario = "";
  new Uint8Array(buffer).forEach((b) => { binario += String.fromCharCode(b); });
  return btoa(binario);
}

function deBase64(texto) {
  const binario = atob(texto);
  const bytes = new Uint8Array(binario.length);
  for (let i = 0; i < binario.length; i += 1) bytes[i] = binario.charCodeAt(i);
  return bytes;
}

async function ocupado(botao, tarefa) {
  const rotulo = botao.textContent;
  botao.disabled = true;
  botao.textContent = "aguarde…";
  try {
    await tarefa();
  } finally {
    botao.disabled = false;
    botao.textContent = rotulo;
  }
}

/* ------------------------------------------------------------- navegação */

function ativarAba(nome) {
  $$(".aba").forEach((aba) => aba.setAttribute("aria-selected", String(aba.dataset.aba === nome)));
  $$(".painel").forEach((painel) => {
    painel.hidden = painel.id !== `painel-${nome}`;
  });
  if (nome === "historico") listarHistorico();
  else if (nome !== "despachar") listarPendrive();
}

$$(".aba").forEach((aba) => {
  aba.addEventListener("click", () => ativarAba(aba.dataset.aba));
});

$$(".filial").forEach((botao) => {
  botao.addEventListener("click", () => {
    estado.filialAtual = Number(botao.dataset.filial);
    $$(".filial").forEach((outro) => {
      outro.setAttribute("aria-pressed", String(outro === botao));
    });
    atualizarRota();
  });
});

function outraFilial() {
  return estado.filialAtual === 1 ? 2 : 1;
}

function atualizarRota() {
  $("#remetente").textContent = estado.filiais[estado.filialAtual] || "—";
  $("#destinatario").textContent = estado.filiais[outraFilial()] || "—";
}

/* ------------------------------------------------------------- despachar */

const mensagem = $("#mensagem");

mensagem.addEventListener("input", () => {
  const total = mensagem.value.length;
  const contador = $("#contador");
  contador.textContent = `${total} caracteres`;
  contador.style.color = total > estado.limite ? PALETA.carimbo : "";
});

$("#botao-resumir").addEventListener("click", (evento) => acionarIa(evento.target, "resumir"));
$("#botao-redigir").addEventListener("click", (evento) => acionarIa(evento.target, "redigir"));

async function acionarIa(botao, acao) {
  mostrarErro("#erro-despachar", "");
  if (!mensagem.value.trim()) {
    mostrarErro("#erro-despachar", acao === "redigir"
      ? "Descreva no campo o que você precisa comunicar."
      : "Escreva o texto longo antes de resumir.");
    return;
  }

  await ocupado(botao, async () => {
    try {
      const r = await chamar("/api/ia", { acao, texto: mensagem.value });
      mensagem.value = r.texto;
      mensagem.dispatchEvent(new Event("input"));
      $("#aviso-ia").textContent = acao === "redigir"
        ? `redigido por ${r.provedor}`
        : `${r.provedor}: ${r.antes} → ${r.depois} caracteres`;
    } catch (erro) {
      mostrarErro("#erro-despachar", erro.message);
    }
  });
}

$("#botao-lacrar").addEventListener("click", (evento) => {
  mostrarErro("#erro-despachar", "");
  ocupado(evento.target, async () => {
    try {
      const pacote = await chamar("/api/despachar", {
        texto: mensagem.value,
        origem: estado.filialAtual,
        destino: outraFilial(),
      });
      estado.pacote = pacote;
      exibirComprovante(pacote);
      listarPendrive();
      listarHistorico();
    } catch (erro) {
      mostrarErro("#erro-despachar", erro.message);
    }
  });
});

function exibirComprovante(pacote) {
  $("#comprovante").hidden = false;
  $("#carimbo-id").textContent = pacote.msg_id.slice(0, 8);
  $("#comprovante-rota").textContent =
    `${estado.filiais[estado.filialAtual]} → ${estado.filiais[outraFilial()]} · ${pacote.nome_arquivo}`;

  $("#medida-original").textContent = `${pacote.bits_originais} bits`;
  $("#medida-comprimida").textContent = `${pacote.bits_comprimidos} bits`;
  $("#medida-reducao").textContent = `${pacote.reducao}%`;
  $("#medida-arquivo").textContent = `${pacote.tamanho_arquivo} bytes`;

  $("#observacao-tamanho").hidden = pacote.tamanho_arquivo * 8 <= pacote.bits_originais;

  $("#arvore-despacho").hidden = true;
  $("#arvore-despacho").innerHTML = "";

  const carimbo = $("#carimbo");
  carimbo.classList.remove("aplicando");
  void carimbo.offsetWidth;                       // reinicia a animação
  carimbo.classList.add("aplicando");

  $("#comprovante").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

$("#botao-baixar").addEventListener("click", () => {
  if (!estado.pacote) return;
  const bytes = deBase64(estado.pacote.arquivo);
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" }));
  const ancora = document.createElement("a");
  ancora.href = url;
  ancora.download = estado.pacote.nome_arquivo;
  ancora.click();
  URL.revokeObjectURL(url);
});

$("#botao-arvore-despacho").addEventListener("click", () => {
  alternarArvore("#arvore-despacho", estado.pacote);
});

/* --------------------------------------------------------------- receber */

async function listarPendrive() {
  try {
    const { arquivos } = await chamar("/api/pendrive");
    preencherLista("#lista-receber", arquivos, abrirRemessa);
    preencherLista("#lista-pericia", arquivos, periciar);
  } catch {
    /* lista vazia é estado válido; silêncio é melhor que ruído aqui */
  }
}

function preencherLista(seletor, arquivos, aoEscolher) {
  const lista = $(seletor);
  lista.innerHTML = "";

  if (!arquivos.length) {
    lista.innerHTML = '<li class="vazio">Nenhuma remessa no pen drive.</li>';
    return;
  }

  arquivos.forEach((arquivo) => {
    const item = document.createElement("li");
    const botao = document.createElement("button");
    botao.type = "button";
    botao.className = "item-arquivo";
    // O nome vem do pen drive, que não é confiável: textContent nunca vira HTML.
    const nome = document.createElement("span");
    nome.textContent = arquivo.nome;
    const peso = document.createElement("span");
    peso.className = "peso";
    peso.textContent = `${arquivo.bytes} bytes`;
    botao.append(nome, peso);
    botao.addEventListener("click", () => aoEscolher({ nome: arquivo.nome }));
    item.appendChild(botao);
    lista.appendChild(item);
  });
}

$("#botao-atualizar").addEventListener("click", listarPendrive);

$("#upload-receber").addEventListener("change", async (evento) => {
  const arquivo = evento.target.files[0];
  if (arquivo) abrirRemessa({ arquivo: paraBase64(await arquivo.arrayBuffer()) });
  evento.target.value = "";
});

$("#upload-pericia").addEventListener("change", async (evento) => {
  const arquivo = evento.target.files[0];
  if (arquivo) periciar({ arquivo: paraBase64(await arquivo.arrayBuffer()) });
  evento.target.value = "";
});

async function abrirRemessa(referencia) {
  mostrarErro("#erro-receber", "");
  try {
    const r = await chamar("/api/receber", referencia);
    estado.recebido = r;

    $("#recebido").hidden = false;
    $("#recebido-rota").textContent = `${r.origem} → ${r.destino}`;
    $("#recebido-texto").textContent = r.texto;
    $("#recebido-data").textContent = r.timestamp;
    $("#recebido-id").textContent = r.msg_id.slice(0, 18) + "…";
    $("#recebido-simbolos").textContent = r.simbolos;
    $("#recebido-bits").textContent = `${r.n_bits} bits`;

    $("#arvore-recebida").hidden = true;
    $("#arvore-recebida").innerHTML = "";
    listarHistorico();
  } catch (erro) {
    $("#recebido").hidden = true;
    mostrarErro("#erro-receber", erro.message);
  }
}

$("#botao-arvore-recebida").addEventListener("click", () => {
  alternarArvore("#arvore-recebida", estado.recebido);
});

/* --------------------------------------------------------------- perícia */

async function periciar(referencia) {
  mostrarErro("#erro-pericia", "");
  try {
    const r = await chamar("/api/periciar", referencia);
    $("#laudo").hidden = false;
    $("#laudo-origem").textContent = r.origem;
    $("#laudo-destino").textContent = r.destino;
    $("#laudo-data").textContent = r.timestamp;
    $("#laudo-id").textContent = r.msg_id;
    $("#laudo-tamanho").textContent =
      `${r.tamanho_bloco} bytes de conteúdo cifrado${r.truncado ? " (primeiros 128 abaixo)" : ""}`;
    $("#laudo-hex").textContent = r.hex;
  } catch (erro) {
    $("#laudo").hidden = true;
    mostrarErro("#erro-pericia", erro.message);
  }
}

/* ------------------------------------------------------------- histórico */

async function listarHistorico() {
  mostrarErro("#erro-historico", "");
  const lista = $("#lista-historico");
  try {
    const { mensagens } = await chamar("/api/historico");
    lista.innerHTML = "";

    if (!mensagens.length) {
      lista.innerHTML = '<li class="vazio">Nenhuma mensagem no histórico.</li>';
      return;
    }

    mensagens.forEach((m) => {
      const item = document.createElement("li");
      const botao = document.createElement("button");
      botao.type = "button";
      botao.className = "item-arquivo";
      botao.innerHTML = `<span>${escapar(m.data)} · ${escapar(m.direcao)} · `
        + `${escapar(m.origem)} → ${escapar(m.destino)}</span>`
        + `<span class="peso">${escapar(m.msg_id.slice(0, 8))}</span>`;
      // Reabre pela mesma rota do pen drive: o servidor decifra com a chave.
      botao.addEventListener("click", () => {
        ativarAba("receber");
        abrirRemessa({ historico: m.msg_id, direcao: m.direcao });
      });
      item.appendChild(botao);
      lista.appendChild(item);
    });
  } catch (erro) {
    mostrarErro("#erro-historico", erro.message);
  }
}

$("#botao-atualizar-historico").addEventListener("click", listarHistorico);

/* ---------------------------------------------------------------- árvore */

function alternarArvore(seletor, dados) {
  const visor = $(seletor);
  if (!dados) return;

  if (!visor.hidden) { visor.hidden = true; return; }

  if (!visor.innerHTML) {
    visor.innerHTML = `<div class="rolagem-arvore">${montarSvg(dados.arvore)}</div>`
      + montarTabela(dados.codigos);
  }
  visor.hidden = false;
}

function montarSvg(raiz) {
  const ESPACO_X = 48;
  const ESPACO_Y = 66;
  const MARGEM = 34;

  let coluna = 0;
  let profundidadeMaxima = 0;

  (function posicionar(no, profundidade) {
    profundidadeMaxima = Math.max(profundidadeMaxima, profundidade);
    if (no.folha) {
      no.x = coluna;
      coluna += 1;
      no.y = profundidade;
      return;
    }
    posicionar(no.esquerda, profundidade + 1);
    if (no.direita) posicionar(no.direita, profundidade + 1);
    no.x = no.direita ? (no.esquerda.x + no.direita.x) / 2 : no.esquerda.x;
    no.y = profundidade;
  })(raiz, 0);

  const largura = Math.max(coluna, 1) * ESPACO_X + MARGEM * 2;
  const altura = (profundidadeMaxima + 1) * ESPACO_Y + MARGEM * 2;
  const px = (no) => MARGEM + no.x * ESPACO_X + ESPACO_X / 2;
  const py = (no) => MARGEM + no.y * ESPACO_Y;

  const partes = [];

  (function ligar(no) {
    if (no.folha) return;
    [[no.esquerda, "0"], [no.direita, "1"]].forEach(([filho, bit]) => {
      if (!filho) return;
      partes.push(
        `<line x1="${px(no)}" y1="${py(no) + 9}" x2="${px(filho)}" y2="${py(filho) - 13}" `
        + `stroke="${PALETA.linha}" stroke-width="1.2"/>`,
        `<text x="${(px(no) + px(filho)) / 2 + (bit === "0" ? -9 : 7)}" `
        + `y="${(py(no) + py(filho)) / 2}" font-size="11" font-family="IBM Plex Mono, monospace" `
        + `fill="${PALETA.carimbo}">${bit}</text>`,
      );
      ligar(filho);
    });
  })(raiz);

  (function nos(no) {
    if (no.folha) {
      const rotulo = no.simbolo === "espaco" ? "␣" : no.simbolo;
      partes.push(
        `<rect x="${px(no) - 15}" y="${py(no) - 13}" width="30" height="30" rx="2" `
        + `fill="${PALETA.papel}" stroke="${PALETA.tinta}" stroke-width="1.4"/>`,
        `<text x="${px(no)}" y="${py(no) + 7}" text-anchor="middle" font-size="14" `
        + `font-family="Archivo, sans-serif" font-weight="600" fill="${PALETA.tinta}">${escapar(rotulo)}</text>`,
        `<text x="${px(no)}" y="${py(no) + 31}" text-anchor="middle" font-size="10" `
        + `font-family="IBM Plex Mono, monospace" fill="${PALETA.linha}">${no.frequencia}</text>`,
      );
      return;
    }
    partes.push(
      `<circle cx="${px(no)}" cy="${py(no)}" r="13" fill="${PALETA.tinta}"/>`,
      `<text x="${px(no)}" y="${py(no) + 4}" text-anchor="middle" font-size="10" `
      + `font-family="IBM Plex Mono, monospace" fill="${PALETA.papel}">${no.frequencia}</text>`,
    );
    nos(no.esquerda);
    if (no.direita) nos(no.direita);
  })(raiz);

  return `<svg viewBox="0 0 ${largura} ${altura}" width="${largura}" height="${altura}" `
    + `role="img" aria-label="Árvore de Huffman da mensagem">${partes.join("")}</svg>`;
}

function montarTabela(codigos) {
  const linhas = codigos.map((linha) => {
    const rotulo = linha.simbolo === "espaco" ? "␣" : escapar(linha.simbolo);
    return `<span><span>${rotulo} <em>${linha.frequencia}×</em></span>`
      + `<span class="bits">${linha.codigo}</span></span>`;
  });
  return `<div class="tabela-codigos">${linhas.join("")}</div>`;
}

function escapar(texto) {
  return String(texto).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ----------------------------------------------------------------- start */

(async function iniciar() {
  try {
    const configuracao = await chamar("/api/configuracao");
    estado.filiais = configuracao.filiais;
    estado.limite = configuracao.limite;
    $("#lacre").textContent = configuracao.lacre;
    atualizarRota();
    listarPendrive();
  } catch (erro) {
    ["#erro-despachar", "#erro-receber", "#erro-pericia", "#erro-historico"]
      .forEach((seletor) => mostrarErro(seletor, erro.message));
  }
})();
