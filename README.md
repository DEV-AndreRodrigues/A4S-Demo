# Smart Safety – Gerador de eventos de demonstração

Ferramenta interna do time comercial da A4 Solutions para gerar eventos que movimentam as telas da plataforma Smart Safety durante demonstrações.

```
index.html                     Aplicação (página única, sem build)
robots.txt / .nojekyll         Bloqueio de indexação / publicação direta no Pages
ponte/
  ponte_smart_safety.py        Ponte local (Python 3, só biblioteca padrão)
  ponte.config.example.json    Modelo de configuração da ponte
  iniciar-ponte.command        Atalho macOS
  iniciar-ponte.bat            Atalho Windows
```

## Como funciona

A página roda no navegador. Duas coisas o navegador não faz sozinho, e por isso cada vendedor roda a **ponte local** no próprio computador:

1. **Consultar a API da Smart Suite**: a API bloqueia chamadas de outros sites (CORS). A ponte faz a consulta por fora do navegador.
2. **Enviar o evento do Botão de Pânico**: o evento entra na plataforma por TCP, e navegador não abre socket TCP.

A ponte escuta só em `127.0.0.1`, aceita só as origens listadas na configuração, só GET nas rotas de colaboradores, locais, dispositivos e códigos de pânico em `*.a4s.io`, e só o frame do Botão de Pânico (type 12 / code 100).

## Publicar no GitHub Pages

1. Crie o repositório na organização (sugestão: `A4Solutions/smart-safety-demo`) e envie o conteúdo desta pasta:
   ```bash
   git init && git add . && git commit -m "Gerador de eventos de demonstração"
   git branch -M main
   git remote add origin git@github.com:A4Solutions/smart-safety-demo.git
   git push -u origin main
   ```
2. No repositório: **Settings > Pages > Build and deployment > Source: Deploy from a branch**, branch `main`, pasta `/ (root)`.
3. Em 1 a 2 minutos o link fica disponível em `https://a4solutions.github.io/smart-safety-demo/`.
4. Confira que `ponte/ponte.config.json` **não** foi enviado (está no `.gitignore`).

> **Visibilidade:** em planos Free/Team, o site do GitHub Pages é **público**, mesmo com repositório privado. Só o GitHub Enterprise Cloud permite restringir o site aos membros da organização (Settings > Pages > Visibility: Private). A senha da tela de entrada é uma barreira contra uso casual, não controle de acesso.

## Preparar o computador do vendedor (uma vez)

1. Ter Python 3 instalado (`python3 --version` no macOS; no Windows, instalar pelo python.org).
2. Baixar a pasta `ponte/` do repositório.
3. Colocar na mesma pasta o arquivo `ponte.config.json` recebido pelo canal interno (não pelo GitHub). Modelo:
   ```json
   {
     "tcp_host": "<host TCP da plataforma>",
     "tcp_port": 0,
     "bridge_port": 8765,
     "allowed_origins": ["null", "https://a4solutions.github.io"]
   }
   ```
   `allowed_origins` precisa conter a origem do site publicado (só protocolo + domínio, sem o caminho do repositório).

## Usar na demonstração

1. Iniciar a ponte: dois cliques em `iniciar-ponte.command` (macOS) ou `iniciar-ponte.bat` (Windows). Deixar a janela aberta.
2. Abrir o link do GitHub Pages e entrar com a senha de acesso.
3. Na primeira vez, o Chrome pode pedir permissão para o site acessar a **rede local**: clicar em **Permitir** (é a conexão com a ponte em `127.0.0.1`).
4. Em **Configuração**: cadastrar token e secret da integração do tenant de demonstração, definir um PIN e clicar em **Testar conexão**.
5. Começar em **Simulação**; mudar para **Envio real** só no tenant de demonstração.

## Segurança

- Token e secret ficam criptografados no navegador (AES-256-GCM, chave derivada do PIN). Nunca são gravados no repositório.
- A senha de acesso fica no código só como hash PBKDF2. Para trocar, gere um hash novo e substitua `GATE` em `index.html`.
- Use uma integração exclusiva do tenant de demonstração, com permissão só de leitura. Revogue em **Integrações** se houver exposição.
- Nunca faça commit de `ponte.config.json`, de tokens, secrets, IPs ou hosts internos.
