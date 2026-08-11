# Automation Dashboard

Painel web em Flask para centralizar e executar automações locais. A aplicação roda em Docker, usa `uv` para dependências, SQLite para histórico de execuções e `threading.Thread` para disparar automações em background sem bloquear a requisição HTTP.

## Tecnologias

- Python 3.12
- Flask
- Gunicorn para execução em produção
- SQLite com `sqlite3`
- Docker e Docker Compose
- `uv`
- Tailwind CSS via CDN
- JavaScript nativo com `fetch`
- Sessão Flask com autenticação por `.env`
- Google APIs para a automação de Obras da CPFL
- Google Sheets/Drive para a automação de Atualização do Drive
- `pandas`, `openpyxl` e `gspread` para leitura da planilha e escrita no Google Sheets
- `requests` para chamadas HTTP externas

## Executar com Docker

Crie um `.env` local com as variáveis necessárias e suba a aplicação:

```bash
docker compose up --build
```

Acesse:

```text
http://localhost:5000
```

O Compose de produção expõe a porta `5000` para o proxy/rede Docker, lê o `.env` por `env_file`, monta credenciais Google como leitura em `/run/secrets/`, monta o diretório de token OAuth em `/run/tokens` como gravável, persiste o SQLite no volume `automation_data` e executa a aplicação com Gunicorn usando um único worker.

Outros comandos:

```bash
docker compose up
docker compose build
docker compose logs -f app
docker compose down
docker compose down -v
```

`docker compose down -v` remove o volume e apaga o histórico persistido em SQLite.

## Executar localmente com uv

```bash
uv sync
uv run flask --app app run --debug
```

Para execução local, exporte as variáveis de ambiente antes de iniciar o Flask. A aplicação não carrega `.env` manualmente nos módulos Python.

Para produção ou simulação local do comando usado no container:

```bash
uv run gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 4 app:app
```

Use somente um worker, porque o bloqueio de execuções, logs em tempo real e estado de automações em andamento ficam em memória dentro do processo Flask.

## Estrutura

```text
.
├── app.py
├── auth.py
├── automation_errors.py
├── automation_registry.py
├── automation_service.py
├── config.py
├── database.py
├── automations/
│   ├── drive/
│   │   ├── runner.py
│   │   ├── row_builder.py
│   │   ├── sheets_client.py
│   │   └── spreadsheet_reader.py
│   └── works_cpfl/
│       ├── main.py
│       ├── runner.py
│       ├── services/
│       │   ├── cpfl_client.py
│       │   ├── environment_validator.py
│       │   ├── evolution_client.py
│       │   ├── gmail_client.py
│       │   ├── google_credentials.py
│       │   └── google_drive_client.py
│       └── utils/
│           └── parse_workes_response.py
├── templates/
│   ├── index.html
│   └── login.html
├── static/
├── tests/
├── upload_service.py
├── data/
├── pyproject.toml
├── uv.lock
├── Dockerfile
└── compose.yaml
```

## Responsabilidades

- `app.py`: instância Flask, handlers HTTP e rotas.
- `auth.py`: validação de credenciais, sessão, CSRF, decorator de autenticação e rate limit de login.
- `automation_registry.py`: cadastro explícito das automações disponíveis.
- `automation_service.py`: controle de execução, thread, bloqueio duplicado, histórico e payload dos cards.
- `automation_service.py`: também captura logs emitidos pela thread da automação para exibição no card durante o polling.
- `automation_errors.py`: erro público seguro para mensagens exibidas no painel.
- `config.py`: leitura centralizada de variáveis de ambiente e caminhos.
- `database.py`: persistência SQLite.
- `upload_service.py`: validação, gravação temporária e limpeza dos uploads `.xlsx`.
- `automations/works_cpfl/runner.py`: ponto de entrada da automação real de Obras da CPFL.
- `automations/drive/runner.py`: ponto de entrada da automação real de Atualização do Drive.

## Autenticação

A aplicação possui uma tela de login em:

```text
GET /login
POST /login
POST /logout
```

Não há cadastro de usuários, banco de usuários ou múltiplos perfis. O login compara exatamente os valores enviados com as variáveis de ambiente:

```text
USER_APP
PASSWORD
```

A comparação usa `hmac.compare_digest()`. A sessão armazena somente:

```python
session["authenticated"] = True
```

A senha não é salva na sessão, no SQLite ou no HTML.

Rotas protegidas:

- `GET /`
- `GET /api/automations`
- `POST /api/automations/<automation_id>/run`

Chamadas de API sem autenticação retornam:

```json
{"error": "Autenticação necessária."}
```

com status `401`. Páginas HTML sem autenticação redirecionam para `/login`.

O logout usa somente `POST /logout` e limpa a sessão com `session.clear()`.

### CSRF

As rotas mutáveis usam um token CSRF simples armazenado na sessão:

- `POST /login` recebe o token por campo oculto;
- `POST /logout` recebe o token por campo oculto;
- `POST /api/automations/<automation_id>/run` recebe o token no header `X-CSRF-Token`.

O JavaScript redireciona para `/login` quando uma API retorna `401`.

### Rate Limit

O login possui rate limit em memória por IP:

```text
5 tentativas em 15 minutos, com bloqueio temporário de 15 minutos
```

Esses valores podem ser ajustados por ambiente. Como o controle fica em memória, ele é perdido ao reiniciar o container e não funciona entre múltiplas réplicas. Para este projeto, mantenha uma única réplica.

### Sessão e Cookies

Configurações aplicadas:

```text
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SAMESITE=Lax
PERMANENT_SESSION_LIFETIME=12 horas
```

`SESSION_COOKIE_SECURE` é configurável por ambiente. Use:

```env
SESSION_COOKIE_SECURE=false
```

em desenvolvimento local sem HTTPS, e:

```env
SESSION_COOKIE_SECURE=true
```

na VPS atrás de HTTPS.

Também há headers básicos:

```text
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy
```

A CSP permite o Tailwind via CDN nesta versão. Para endurecer a política em produção, o ideal é substituir o Tailwind CDN por um build local.

## Automação Obras da CPFL

O botão do card `Obras da CPFL` executa:

```python
automations.works_cpfl.runner.run()
```

Contrato:

```python
def run():
    ...
```

`run()` não recebe argumentos, não cria threads, não acessa objetos Flask e não encerra o processo. Retorno normal significa sucesso; exceção significa erro e será tratada pelo `automation_service.py`.

Fluxo atual:

1. valida variáveis de ambiente obrigatórias;
2. autentica Google com credenciais e token OAuth;
3. consulta obras programadas na API da CPFL;
4. busca PDFs correspondentes no Gmail por TES/TLE;
5. publica ou atualiza PDFs no Google Drive;
6. monta a mensagem;
7. envia a mensagem pela API Evolution.

O fluxo antigo de scraping HTML, BeautifulSoup, bs4, TinyURL e encurtamento de links foi removido.

Durante a execução pelo painel, os logs emitidos pela automação aparecem no card em tempo real. Esses logs são mantidos em memória e acompanham a última execução desde que o processo Flask não seja reiniciado.

Execução manual opcional:

```bash
uv run python -m automations.works_cpfl.main
```

## Automação Atualização do Drive

O botão do card `Atualização do Drive` abre um modal para envio da planilha de backlog. A automação não procura mais arquivos `.xlsx` na raiz do projeto e não depende do diretório atual.

Contrato:

```python
from pathlib import Path


def run(input_file: Path) -> None:
    ...
```

`input_file` é um arquivo temporário já validado pelo backend. O runner lê a planilha, consulta os protocolos existentes na aba configurada do Google Sheets e adiciona apenas novas linhas.

Validações do upload:

- campo `file` obrigatório;
- somente um arquivo;
- extensão única `.xlsx`;
- limite configurável por `MAX_UPLOAD_SIZE_MB`, padrão `20`;
- limite de expansão do XLSX por `MAX_XLSX_UNCOMPRESSED_SIZE_MB`, padrão `100`;
- limite de dimensões por `MAX_SPREADSHEET_ROWS` e `MAX_SPREADSHEET_CELLS`;
- abertura real do arquivo com `openpyxl`;
- colunas obrigatórias do fluxo legado;
- pelo menos um registro antes da primeira linha vazia em `SERVICO`.

Os arquivos enviados são salvos em diretórios exclusivos dentro de `UPLOAD_TEMP_DIR`, cujo padrão é `data/uploads/`. O arquivo e o diretório temporário são removidos em `finally` após sucesso ou erro. Na inicialização, uploads antigos dentro desse diretório também são limpos de forma conservadora.

O fluxo antigo de projeto independente foi incorporado ao ambiente principal. Foram removidos o `pyproject.toml`, `uv.lock`, `.venv`, busca automática por `.xlsx`, leitura local de `.env`, uso de `rich` e movimentação para `processed/`.

## Variáveis de ambiente

Obrigatórias para autenticação:

```text
USER_APP
PASSWORD
SECRET_KEY
```

`SECRET_KEY` deve ser longa e aleatória, com pelo menos 32 caracteres, e deve ser diferente de `PASSWORD`. Gere uma chave com:

```bash
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Exemplo sem dados reais:

```env
USER_APP=admin
PASSWORD=use-uma-senha-longa
SECRET_KEY=gere-uma-chave-aleatoria
SESSION_COOKIE_SECURE=false
TRUST_PROXY=false
```

Para produção atrás de proxy reverso com HTTPS:

```env
SESSION_COOKIE_SECURE=true
TRUST_PROXY=true
```

`USER_APP` foi usado para evitar conflito com a variável padrão `USER` comum em Linux e containers. Se credenciais forem alteradas no `.env`, reinicie o container.

Obrigatórias para Obras da CPFL:

```text
GOOGLE_CREDENTIALS_FILE
GOOGLE_TOKEN_DIR
GOOGLE_TOKEN_FILE
GOOGLE_DRIVE_FOLDER_ID
GMAIL_USER_ID
GMAIL_QUERY
SEND_NUMBERS
EVO_API_KEY
EVO_URL
INSTANCE
```

Opcionais:

```text
CPFL_API_URL
GMAIL_SENDER
GMAIL_LABEL
GMAIL_MAX_RESULTS
GOOGLE_DRIVE_SHARE_TYPE
GOOGLE_DRIVE_SHARE_ROLE
GOOGLE_DRIVE_SHARE_DOMAIN
GOOGLE_OAUTH_INTERACTIVE
```

Obrigatórias para Atualização do Drive:

```text
DRIVE_UPDATE_GOOGLE_CREDENTIALS_FILE
DRIVE_UPDATE_SHEET_NAME
DRIVE_UPDATE_WORKSHEET_NAME
```

Opcional:

```text
MAX_UPLOAD_SIZE_MB
MAX_XLSX_UNCOMPRESSED_SIZE_MB
MAX_SPREADSHEET_ROWS
MAX_SPREADSHEET_COLUMNS
MAX_SPREADSHEET_CELLS
UPLOAD_TEMP_DIR
```

Configure `GMAIL_SENDER` ou `GMAIL_LABEL` para limitar a busca dos PDFs no Gmail.

No Docker, `GOOGLE_CREDENTIALS_FILE` e `DRIVE_UPDATE_GOOGLE_CREDENTIALS_FILE` no `.env` devem apontar para arquivos existentes no host e sao montados como somente leitura. `GOOGLE_TOKEN_DIR` deve apontar para o diretorio persistente que contem `token.google.json`; esse diretorio e montado como gravavel porque o refresh OAuth regrava o token. `GOOGLE_TOKEN_FILE` continua util para execucao local e geracao manual do token, mas o Compose nao usa esse valor como origem de volume e sobrescreve a variavel dentro do container.

Exemplo local:

```env
GOOGLE_CREDENTIALS_FILE=$HOME/.config/obras-cpfl/credentials.google.json
DRIVE_UPDATE_GOOGLE_CREDENTIALS_FILE=$HOME/.config/obras-cpfl/drive_update_credentials.json
GOOGLE_TOKEN_DIR=$HOME/.config/obras-cpfl/tokens
GOOGLE_TOKEN_FILE=$HOME/.config/obras-cpfl/tokens/token.google.json
GOOGLE_OAUTH_INTERACTIVE=false
```

O Compose monta esses caminhos no container como:

```text
/run/secrets/google_credentials.json
/run/secrets/drive_update_credentials.json
/run/tokens/token.google.json
```

e sobrescreve as variáveis dentro do container para esses caminhos.

Para gerar ou regerar o token OAuth da automacao CPFL, use uma sessao local com navegador e a credencial OAuth configurada no Google Cloud para app instalado/desktop. O app pode estar com tela de consentimento em producao; o ponto importante e gerar o token com os mesmos escopos fixos usados pelo codigo (`gmail.readonly` e `drive.file`):

```bash
mkdir -p $HOME/.config/obras-cpfl/tokens
chmod 700 $HOME/.config/obras-cpfl/tokens

GOOGLE_CREDENTIALS_FILE=/caminho/seguro/google_credentials.json \
GOOGLE_TOKEN_FILE=$HOME/.config/obras-cpfl/tokens/token.google.json \
uv run python -m automations.works_cpfl.services.google_credentials

chmod 600 $HOME/.config/obras-cpfl/tokens/token.google.json
```

Em desenvolvimento, o Docker apenas monta `GOOGLE_TOKEN_DIR` em `/run/tokens`; a automacao usa `/run/tokens/token.google.json` e renova esse arquivo quando fizer refresh.

Em producao, gere ou regenere o token fora da VPS/container, copie `token.google.json` para o diretorio persistente configurado em `GOOGLE_TOKEN_DIR` na VPS e reinicie/recrie o container se necessario. Depois disso, o refresh futuro regrava o mesmo arquivo montado em `/run/tokens/token.google.json`.

Mantenha `GOOGLE_OAUTH_INTERACTIVE=false` nos containers. A producao nao deve abrir navegador nem iniciar OAuth interativo; se o token estiver ausente, revogado, expirado sem `refresh_token` ou sem os escopos corretos, a validacao falha pedindo a geracao manual. Nao monte mais `token.google.json` diretamente como bind mount de arquivo; se esse arquivo for apagado nesse modelo antigo, o Docker pode recriar o caminho como diretorio no host.

Não versione `.env`, credenciais Google ou tokens. `.dockerignore` e `.gitignore` excluem `.env`, `data/google/`, `data/drive/`, `data/uploads/` e arquivos comuns de credenciais/tokens.

## Persistência

O histórico de execuções fica em:

```text
data/automations.db
```

No Docker, o caminho é `/app/data/automations.db` e fica no volume `automation_data`.

Se a aplicação reiniciar durante uma execução, registros `running` são marcados como `error` com:

```text
Execução interrompida por reinicialização da aplicação.
```

## API

- `GET /`
- `GET /login`
- `POST /login`
- `POST /logout`
- `GET /api/automations`
- `POST /api/automations/<automation_id>/run`

IDs:

- `cpfl-works`
- `drive-update`

Status esperados:

- `200` para consultas;
- `202` ao iniciar;
- `302` para redirecionamentos de login/logout;
- `400` para CSRF inválido;
- `401` para API sem autenticação ou login inválido;
- `403` para POST de origem incompatível;
- `404` para automação inexistente;
- `409` quando já está em execução;
- `413` quando o upload excede o limite;
- `422` quando o arquivo `.xlsx` é inválido ou não possui a estrutura esperada;
- `500` para erro inesperado.

## Adicionar Automações

Crie um módulo com:

```python
def run():
    ...
```

Cadastre em `automation_registry.py` com `id`, `name`, `description` e `runner`. A automação deve propagar exceções e deixar thread, histórico, duração e status para o `automation_service.py`.

Para automações que exigem arquivo de entrada, cadastre o runner e trate o upload na rota/serviço correspondente. O runner deve receber explicitamente um `Path`; não use caminhos enviados pelo usuário nem procure arquivos no filesystem.

## Decisões de escopo

Este projeto foi projetado deliberadamente para uso pessoal, com um único usuário e baixa frequência de execução, em torno de duas ou três automações manuais por dia. A prioridade é manter operação simples, baixo custo e manutenção direta, sem infraestrutura distribuída desnecessária.

Por esse motivo, algumas escolhas são intencionais:

- SQLite persistido em volume em vez de banco externo.
- Threads locais em vez de fila distribuída.
- Gunicorn com um único worker para manter bloqueios, logs em tempo real e estado de execução consistentes em memória.
- Autenticação simples por variáveis de ambiente, sem cadastro ou gerenciamento de usuários.
- Ausência de Redis, Celery, múltiplas réplicas e escalabilidade horizontal.
- Docker, Docker Compose e `uv` como base de execução reprodutível na VPS.

Essas decisões são adequadas ao volume atual e deixam claro o escopo do sistema. Se o projeto evoluir para múltiplos usuários, execuções frequentes, SLA maior ou múltiplas réplicas, a arquitetura deverá ser revista.

Para publicação na internet, mantenha a aplicação atrás de proxy reverso com HTTPS e firewall, use `SESSION_COOKIE_SECURE=true`, habilite `TRUST_PROXY=true` somente atrás de proxy confiável e não exponha diretamente a porta do Flask.

A Atualização do Drive escreve em uma planilha externa configurada por ambiente; por isso, os testes automatizados substituem runners e não fazem chamadas reais ao Google.
