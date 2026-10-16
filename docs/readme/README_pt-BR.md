# Copy APP

**Idioma:** Português (Brasil) · [Todos os idiomas](../../README.md#languages) · [English](../../README.md)

O Copy APP coleta evidências do pacote, da interface, do sandbox e do comportamento em execução de um app instalado em um iPhone com jailbreak. Ele produz um relatório de análise com referências às fontes e ajuda a criar um app iOS independente que reproduz funções selecionadas para comparação no dispositivo real.

## Como funciona

Um agente de programação controla a CLI do Copy APP no Mac. OpenSSH, Frida, iOS MCP ou o iCTRL opcional coletam evidências do iPhone selecionado. Quando necessário, Ghidra ou Hopper analisam código nativo no Mac. O relatório revisado e `feature-spec.json` orientam a nova implementação; os mesmos fluxos são executados no app original e no novo, e as capturas de tela são examinadas. O [diagrama de arquitetura e a instalação completa](../../README.md#how-it-works) estão em inglês.

## Início rápido

Instale Python 3.9+ no Mac, conecte um iPhone com jailbreak por USB, confirme a confiança e execute:

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
.venv/bin/copyapp onboard
```

Comece pela [primeira inspeção via USB](../../README.md#install-and-run-your-first-survey). A análise aprofundada também precisa de SSH, Frida e um serviço de interface no telefone.

## Princípios e contribuição

Registre as evidências antes de interpretá-las e deixe as incertezas explícitas. Validar fluxos escolhidos não comprova equivalência completa entre apps. Aceitamos relatos reproduzíveis, testes, scripts de UI e traduções. Não envie IPAs, credenciais ou dados brutos do sandbox para o Git. Veja o [guia de contribuição](../../CONTRIBUTING.md).

O iPhone XR com iOS 16.1.1 foi validado; iOS 17 e 26 ainda não foram testados. O idioma da documentação não muda o idioma da CLI nem dos relatórios.
