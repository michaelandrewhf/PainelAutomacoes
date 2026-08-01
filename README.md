# Automation Dashboard

Painel web em Flask para centralizar e executar automações locais. A aplicação roda em Docker, usa `uv` para dependências, SQLite para histórico de execuções e `threading.Thread` para disparar automações em background sem bloquear a requisição HTTP.

## Tecnologias

- Python 3.12
- Flask
- SQLite com `sqlite3`
- Docker e Docker Compose
- `uv`
- Tailwind CSS via CDN
- JavaScript nativo com `fetch`
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

O Compose publica a porta apenas em `127.0.0.1:5000`, lê o `.env` por `env_file`, monta credenciais/token Google como leitura em `/run/secrets/` e persiste o SQLite no volume `automation_data`.

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

## Estrutura

```text
.
├── app.py
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
- `automation_registry.py`: cadastro explícito das automações disponíveis.
- `automation_service.py`: controle de execução, thread, bloqueio duplicado, histórico e payload dos cards.
- `automation_service.py`: também captura logs emitidos pela thread da automação para exibição no card durante o polling.
- `automation_errors.py`: erro público seguro para mensagens exibidas no painel.
- `config.py`: leitura centralizada de variáveis de ambiente e caminhos.
- `database.py`: persistência SQLite.
- `upload_service.py`: validação, gravação temporária e limpeza dos uploads `.xlsx`.
- `automations/works_cpfl/runner.py`: ponto de entrada da automação real de Obras da CPFL.
- `automations/drive/runner.py`: ponto de entrada da automação real de Atualização do Drive.

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

Obrigatórias para Obras da CPFL:

```text
GOOGLE_CREDENTIALS_FILE
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
MAX_SPREADSHEET_CELLS
UPLOAD_TEMP_DIR
```

Configure `GMAIL_SENDER` ou `GMAIL_LABEL` para limitar a busca dos PDFs no Gmail.

No Docker, `GOOGLE_CREDENTIALS_FILE`, `GOOGLE_TOKEN_FILE` e `DRIVE_UPDATE_GOOGLE_CREDENTIALS_FILE` no `.env` devem apontar para arquivos existentes no host. A credencial `credentials.json` trazida com a automação do Drive deve ficar no mesmo diretório seguro usado pela credencial da CPFL, com nome próprio, e ser referenciada por `DRIVE_UPDATE_GOOGLE_CREDENTIALS_FILE`.

O Compose monta esses arquivos no container como:

```text
/run/secrets/google_credentials.json
/run/secrets/google_token.json
/run/secrets/drive_update_credentials.json
```

e sobrescreve as variáveis dentro do container para esses caminhos.

Para gerar ou renovar um token OAuth, execute a autenticação fora do container ou ajuste temporariamente a estratégia de OAuth. A execução pelo painel assume que o token já existe e é somente leitura.

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
- `GET /api/automations`
- `POST /api/automations/<automation_id>/run`

IDs:

- `cpfl-works`
- `drive-update`

Status esperados:

- `200` para consultas;
- `202` ao iniciar;
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

## Limitações

- Threads locais não substituem uma fila de tarefas.
- SQLite é adequado para uso local e baixa concorrência.
- O controle em memória pressupõe um único processo Flask.
- O Compose padrão não usa modo debug por causa das credenciais reais montadas no container.
- Antes de expor na internet, adicione autenticação, autorização, CSRF completo, HTTPS, proxy reverso, servidor WSGI adequado e uma estratégia de background mais robusta.
- A Atualização do Drive escreve em uma planilha externa configurada por ambiente; testes automatizados não fazem chamadas reais ao Google.
