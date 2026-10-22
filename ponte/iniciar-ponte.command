#!/bin/bash
# macOS: dê dois cliques para iniciar a ponte (na 1ª vez: botão direito > Abrir).
cd "$(dirname "$0")"
if [ ! -f ponte.config.json ]; then
  echo "Falta o arquivo ponte.config.json nesta pasta. Peça ao time de Produto."
  read -n 1 -s -r -p "Pressione qualquer tecla para fechar..."; exit 1
fi
python3 ponte_smart_safety.py
