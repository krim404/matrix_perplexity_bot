FROM python:3.9

COPY requirements.txt /opt/

WORKDIR /opt
RUN pip install -r requirements.txt

COPY perplexity_ai_llm.py /opt/
COPY run.sh /opt/
RUN chmod -R 777 /opt/run.sh
COPY gpt.py /opt/
COPY bot.py /opt/

CMD ["/opt/run.sh"]