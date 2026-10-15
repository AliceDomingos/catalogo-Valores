#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto Elétrica GP — Extrator de Catálogo de Peças (PDF -> JSON)
Lê todos os PDFs de tabelas de preços (padrão TGA Sistemas) da pasta atual
ou subpastas de categorias (IDN, IDR, RTR, ETR, BNR, BRC) e gera o arquivo
`banco_de_dados.json` otimizado para busca instantânea no Frontend.
"""

import os
import re
import json
from datetime import datetime

# Tenta usar pdfplumber (recomendado) com fallback automático para pypdf
try:
    import pdfplumber
    USAR_PDFPLUMBER = True
except ImportError:
    USAR_PDFPLUMBER = False
    import pypdf

try:
    import pandas as pd
    USAR_PANDAS = True
except ImportError:
    USAR_PANDAS = False

CATEGORIAS_INFO = {
    "IDN": "Induzido Novo",
    "IDR": "Induzidos Recon",
    "RTR": "Rotores",
    "ETR": "Estatores",
    "BNR": "Bobinas",
    "BRC": "Bobinas na Carcaça",
}

# Regex calibrada para as linhas de peças do TGA Sistemas:
# Trata inclusive casos onde o Nome Fantasia encosta na Unidade (ex: "2044CUN" ou "CARCAÇAPC")
REGEX_LINHA_PECA = re.compile(
    r"^(?P<codigo>\d{6})\s+"
    r"(?P<nome>.+?)"
    r"(?:\s+|(?<=[^\s]))(?P<und>UN\.\.|UND|KIT|PC|UN|JG)\s+"
    r"(?:(?P<ref2>(?:IDN|IDR|RTR|ETR|BNR|BRC)(?:\s*[A-Z0-9/\-\.]+)?)\s+)?"
    r"(?:(?P<fab>DIVERSOS)\s+)?"
    r"(?P<preco>\d{1,3}(?:\.\d{3})*,\d{3})$"
)


def detectar_categoria(caminho_arquivo: str) -> str:
    """Identifica a sigla da categoria pelo nome da pasta ou nome do arquivo PDF."""
    partes = caminho_arquivo.upper().replace("\\", "/").split("/")
    for parte in reversed(partes):
        for sigla in CATEGORIAS_INFO:
            if parte.startswith(sigla) or f" {sigla}" in parte or f"_{sigla}" in parte:
                return sigla
    return "IDN"


def converter_preco_float(preco_str: str) -> float:
    """Converte '428,000' ou '1.250,000' para float 428.0."""
    return float(preco_str.replace(".", "").replace(",", "."))


def formatar_brl(valor: float) -> str:
    """Formata float para padrão monetário brasileiro 'R$ 428,00'."""
    if valor <= 0:
        return "Sob Consulta"
    inteiro = int(valor)
    centavos = int(round((valor - inteiro) * 100))
    inteiro_str = f"{inteiro:,}".replace(",", ".")
    return f"R$ {inteiro_str},{centavos:02d}"


def extrair_texto_pdf(caminho_pdf: str) -> list[str]:
    """Extrai o texto de todas as páginas do PDF usando pdfplumber ou pypdf."""
    linhas = []
    if USAR_PDFPLUMBER:
        with pdfplumber.open(caminho_pdf) as pdf:
            for pagina in pdf.pages:
                texto = pagina.extract_text() or ""
                linhas.extend(texto.split("\n"))
    else:
        reader = pypdf.PdfReader(caminho_pdf)
        for pagina in reader.pages:
            texto = pagina.extract_text() or ""
            linhas.extend(texto.split("\n"))
    return linhas


def processar_pasta_pdfs(diretorio_base: str = ".", arquivo_saida: str = "banco_de_dados.json") -> dict:
    """Percorre a pasta (e subpastas), extrai todas as peças e salva o JSON."""
    arquivos_pdf = []
    for raiz, _, arquivos in os.walk(diretorio_base):
        for arq in sorted(arquivos):
            if arq.lower().endswith(".pdf"):
                arquivos_pdf.append(os.path.join(raiz, arq))

    if not arquivos_pdf:
        print(f"[AVISO] Nenhum arquivo PDF encontrado em '{os.path.abspath(diretorio_base)}'.")
        return {}

    registros = []
    data_tabela = None

    for caminho_pdf in arquivos_pdf:
        nome_arq = os.path.basename(caminho_pdf)
        cat_padrao = detectar_categoria(caminho_pdf)
        linhas = extrair_texto_pdf(caminho_pdf)
        cont_arq = 0

        for linha_bruta in linhas:
            linha = linha_bruta.strip()
            if not data_tabela:
                m_data = re.search(r"(\d{2}/\d{2}/\d{4})", linha)
                if m_data:
                    data_tabela = m_data.group(1)

            if not re.match(r"^\d{6}\s+", linha):
                continue

            match = REGEX_LINHA_PECA.match(linha)
            if match:
                d = match.groupdict()
                ref2 = (d["ref2"] or "").strip()
                sigla_cat = ref2.split()[0] if (ref2 and ref2.split()[0] in CATEGORIAS_INFO) else cat_padrao
                if not ref2:
                    ref2 = sigla_cat

                preco_num = converter_preco_float(d["preco"])
                und_limpa = d["und"].replace("..", "").strip()
                if und_limpa == "UND":
                    und_limpa = "UN"

                registros.append({
                    "codigo": d["codigo"].strip(),
                    "nome": re.sub(r"\s+", " ", d["nome"].strip()),
                    "unidade": und_limpa,
                    "categoria": sigla_cat,
                    "categoria_nome": CATEGORIAS_INFO.get(sigla_cat, "Outros"),
                    "referencia": ref2,
                    "fabricante": (d["fab"] or "DIVERSOS").strip(),
                    "preco": round(preco_num, 2),
                    "preco_formatado": formatar_brl(preco_num),
                    "preco_original": d["preco"],
                    "arquivo_origem": nome_arq,
                })
                cont_arq += 1

        print(f"  [OK] {nome_arq:<18} -> {cont_arq:>4} peças extraídas ({cat_padrao})")

    # Se pandas estiver disponível, higieniza duplicatas mantendo o registro mais recente
    if USAR_PANDAS and registros:
        df = pd.DataFrame(registros)
        df = df.drop_duplicates(subset=["codigo", "referencia"], keep="last")
        registros = df.to_dict(orient="records")

    ordem_cat = {sigla: i for i, sigla in enumerate(CATEGORIAS_INFO.keys())}
    registros.sort(key=lambda x: (ordem_cat.get(x["categoria"], 99), x["referencia"], x["codigo"]))

    payload = {
        "empresa": "Auto Elétrica GP",
        "sistema": "Catálogo Rápido de Peças",
        "ultima_atualizacao": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "data_tabela": data_tabela or datetime.now().strftime("%d/%m/%Y"),
        "total_itens": len(registros),
        "categorias": [
            {
                "sigla": sigla,
                "nome": nome,
                "total": sum(1 for p in registros if p["categoria"] == sigla),
            }
            for sigla, nome in CATEGORIAS_INFO.items()
        ],
        "pecas": registros,
    }

    with open(arquivo_saida, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("=" * 65)
    print(f"[SUCESSO] '{arquivo_saida}' gerado com {len(registros)} peças!")
    print("=" * 65)
    return payload


if __name__ == "__main__":
    print("=" * 65)
    print(" AUTO ELÉTRICA GP - EXTRATOR DE TABELAS DE PREÇOS (PDF -> JSON)")
    print("=" * 65)
    if processar_pasta_pdfs(".", "banco_de_dados.json"):
        # Gera também o banco_de_dados.enc, que é o arquivo publicado no site
        from criptografar_catalogo import criptografar_catalogo
        criptografar_catalogo("banco_de_dados.json", "banco_de_dados.enc")
