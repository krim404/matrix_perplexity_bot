# Matrix ChatBot with LLM Integration

This Python code implements a chatbot that communicates using the Matrix messaging protocol and utilizes Large Language Models (LLMs) from Perplexity AI for generating responses.

**WARNING: This code is intended for educational and reference purposes only and should NOT be executed directly. It may contain security vulnerabilities or other issues that could lead to unintended consequences if used in a production environment.**

## Overview

The chatbot consists of two main components:

1. `gpt.py`: This file contains the core functionality of the chatbot, including the integration with the Matrix protocol and the LLM models from Perplexity AI.

2. `bot.py`: This file implements additional features such as user registration, token management, and email sending capabilities.

The chatbot can handle various commands, including:

- `!invite`: Generates a registration token and sends an invitation email to the specified email address.
- `!reset`: Clears the conversation history.
- `!internet`: Triggers a response from the LLM model trained for general knowledge with internet access.
- `!devel`: Triggers a response from the LLM model trained for code and development-related tasks.

## Dependencies

The chatbot relies on several Python libraries and packages, including:

- `nio`: A Python library for interacting with the Matrix protocol.
- `langchain`: A framework for building applications with large language models.
- `markdown`: A library for converting Markdown-formatted text to HTML.
- `requests`: A library for making HTTP requests.
- `smtplib`: A library for sending emails via SMTP.

The required dependencies are listed in the `requirements.txt` file.

## Configuration

The chatbot requires several environment variables to be set for proper configuration. These variables include:

- `HOMESERVER`: The URL of the Matrix homeserver.
- `TOKEN`: The access token for the chatbot user.
- `USER_ID`: The user ID of the chatbot user.
- `PERPLEXITY_API_KEY`: The API key for accessing Perplexity AI's LLM models.
- `REGISTER`: The URL for user registration.
- `INTERN_SERVER`: The URL of the internal Matrix server (admin).
- `TOKEN_ADMIN`: The access token for the admin user.
- `SMTP_SERVER`: The SMTP server address for sending emails.
- `SMTP_PORT`: The SMTP server port.
- `SMTP_EMAIL`: The email address used for sending emails.
- `SMTP_PASS`: The password for the email account.

## Usage

The chatbot is designed to be run as a Docker container using the provided `docker-compose.yml` file. Before running the container, ensure that the required environment variables are set in the `env` file.

To start the chatbot, run the following command:

```
docker-compose up -d
```

This will build the Docker image and start the container in detached mode.

Once the container is running, the chatbot will automatically join any rooms it is invited to and start responding to messages based on the configured commands and LLM models.

## Disclaimer

Please note that this code is provided as-is and may contain security vulnerabilities or other issues. It is strongly recommended to thoroughly review and test the code before using it in a production environment. Additionally, the use of this code may be subject to the terms and conditions of the respective libraries and services used (e.g., Perplexity AI, Matrix, etc.).
