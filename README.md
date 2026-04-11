# Bot de Entrada e Saida para Discord

Bot simples em Python com discord.py para configurar mensagens de boas-vindas e saida usando slash command, interface com Select e armazenamento em SQLite.

## Funcionalidades

- Mensagem automatica quando um membro entra no servidor
- Mensagem automatica quando um membro sai do servidor
- Configuracao por slash command com menu interativo
- Teste de mensagem de entrada e saida
- Visualizacao da configuracao atual
- Remocao separada da configuracao de entrada ou saida
- Banco de dados SQLite criado automaticamente

## Estrutura

```text
.
|-- main.py
|-- bot.db
|-- .env
`-- cogs/
	`-- entry.py
```

## Requisitos

- Python 3.10+
- Biblioteca discord.py
- python-dotenv

## Instalacao

```bash
python -m venv .venv
.venv\Scripts\activate
pip install discord.py python-dotenv
```

## Configuracao

Crie um arquivo `.env` na raiz do projeto com:

```env
TOKEN=seu_token_do_bot
```

Tambem ative no Discord Developer Portal:

- Server Members Intent
- Message Content Intent, se for usar comandos por prefixo depois

## Como rodar

```bash
python main.py
```

Na inicializacao o bot:

- cria o arquivo `bot.db` se ele nao existir
- cria as tabelas necessarias
- carrega automaticamente todos os cogs da pasta `cogs`
- sincroniza os slash commands

## Comando atual

### `/setup`

Abre um menu com as opcoes:

- Configurar Boas-Vindas
- Configurar Saida
- Testar Boas-Vindas
- Testar Saida
- Ver Configuracao
- Remover Boas-Vindas
- Remover Saida

## Placeholder de mensagem

Voce pode usar:

- `{member}` para mencionar ou mostrar o membro na mensagem

Exemplo:

```text
Bem-vindo ao servidor, {member}!
```

## Banco de dados

O projeto usa SQLite com a tabela principal `guild_settings`, onde ficam salvos:

- `guild_id`
- `welcome_channel_id`
- `welcome_message`
- `exit_channel_id`
- `exit_message`

## Observacoes

- O bot usa modais para salvar as mensagens.
- O canal e informado pelo ID do canal.
- Apenas usuarios com permissao de gerenciar servidor podem usar o comando de configuracao.

## Proximas melhorias

- Aceitar selecao direta de canal em vez de ID manual
- Adicionar embed customizado para entrada e saida
- Separar utilitarios de banco em um modulo proprio
- Adicionar comando para resetar toda a configuracao do servidor
