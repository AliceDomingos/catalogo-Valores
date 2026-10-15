#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto Elétrica GP — Criptografia do Catálogo (JSON -> .enc)
Lê o `banco_de_dados.json` (gerado pelo extrair_catalogo.py) e gera o
`banco_de_dados.enc`, que é o ÚNICO arquivo de dados que deve ir para o
GitHub Pages. Sem a senha, o conteúdo do .enc é ilegível.

Algoritmo: AES-256-GCM com chave derivada da senha via PBKDF2-SHA256.
O index.html faz o processo inverso no navegador (Web Crypto API).

Requer: pip install cryptography
"""

import os
import sys
import json
import base64
import getpass
import hashlib

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    print("[ERRO] Biblioteca 'cryptography' não instalada. Rode: pip install cryptography")
    sys.exit(1)

# Precisa ser igual ao que o index.html espera (ele lê o valor do próprio .enc)
ITERACOES_PBKDF2 = 600_000
TAMANHO_MINIMO_SENHA = 12


def derivar_chave(senha: str, salt: bytes, iteracoes: int) -> bytes:
    """Transforma a senha em uma chave AES de 256 bits."""
    return hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, iteracoes, dklen=32)


def pedir_senha() -> str:
    """Lê a senha da variável de ambiente GP_SENHA ou pede no terminal (com confirmação)."""
    senha = os.environ.get("GP_SENHA")
    if senha:
        return senha

    while True:
        senha = getpass.getpass("Digite a senha do catálogo (não aparece ao digitar): ")
        if len(senha) < TAMANHO_MINIMO_SENHA:
            print(f"  [AVISO] Use pelo menos {TAMANHO_MINIMO_SENHA} caracteres. Ex: bobina-verde-titan-2026")
            continue
        if getpass.getpass("Confirme a senha: ") != senha:
            print("  [AVISO] As senhas não conferem. Tente novamente.")
            continue
        return senha


def criptografar_catalogo(arquivo_entrada: str = "banco_de_dados.json",
                          arquivo_saida: str = "banco_de_dados.enc",
                          senha: str | None = None) -> None:
    """Criptografa o JSON do catálogo e salva o arquivo .enc."""
    if not os.path.exists(arquivo_entrada):
        print(f"[ERRO] '{arquivo_entrada}' não encontrado. Rode antes: python extrair_catalogo.py")
        sys.exit(1)

    with open(arquivo_entrada, "r", encoding="utf-8") as f:
        dados = json.load(f)

    senha = senha or pedir_senha()

    salt = os.urandom(16)
    iv = os.urandom(12)
    chave = derivar_chave(senha, salt, ITERACOES_PBKDF2)

    texto_puro = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    # AESGCM.encrypt devolve ciphertext + tag de 16 bytes, formato que o Web Crypto espera
    cifrado = AESGCM(chave).encrypt(iv, texto_puro, None)

    payload = {
        "versao": 1,
        "algoritmo": "AES-256-GCM",
        "kdf": "PBKDF2-SHA256",
        "iteracoes": ITERACOES_PBKDF2,
        "salt": base64.b64encode(salt).decode("ascii"),
        "iv": base64.b64encode(iv).decode("ascii"),
        "dados": base64.b64encode(cifrado).decode("ascii"),
    }

    with open(arquivo_saida, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    print("=" * 65)
    print(f"[SUCESSO] '{arquivo_saida}' gerado ({len(dados.get('pecas', []))} peças criptografadas).")
    print(f"  Suba para o GitHub: index.html + {arquivo_saida}")
    print(f"  NUNCA suba: {arquivo_entrada} nem os PDFs")
    print("=" * 65)


if __name__ == "__main__":
    print("=" * 65)
    print(" AUTO ELÉTRICA GP - CRIPTOGRAFIA DO CATÁLOGO (JSON -> .enc)")
    print("=" * 65)
    criptografar_catalogo()
