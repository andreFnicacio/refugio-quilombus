# 📋 CHANGELOG // O REFÚGIO

Registro formal de alterações, correções de bugs, melhorias de arquitetura e novas funcionalidades implementadas no monólito.

---

## [v1.2.0] - 2026-10-11

### 🚨 Bugfixes
* **Resolução da coluna Geek/Nerd no `/radar` com integração ao Omelete:**
  - Substituída a fonte RSS legada que causava falhas e desatualizações constantes na coluna Geek/Nerd por um crawler/parser dinâmico e resiliente conectado diretamente ao portal [Omelete](https://www.omelete.com.br/).
  - Implementada extração robusta de elementos com tratamento completo para títulos de matérias, normalização de links de destino absolutos/relativos, conversão de imagens de capa em CDN (suporte a protocolo schema-relative `//` e lazy loading) e conversão precisa de datas de publicação (`data-published` ISO 8601 e RFC 2822).
  - Implementado mecanismo de transporte resiliente com dupla camada de conexão (`httpx` primário com fallback transparente para `curl` nativo do sistema para contornar limitações de handshake TLS/Akamai) e contingência com *fallback* estrito de 5 itens offline, prevenindo que a página `/radar` quebre caso a rede externa fique indisponível.

### 🎥 Features
* **Renderizador de links e thumbnails de vídeo do YouTube no `/diario` e posts:**
  - Criação do módulo utilitário `media_utils.py` com o extrator `extract_youtube_id()`, suportando todos os formatos padrão: `youtube.com/watch?v=ID`, `youtu.be/ID`, `youtube.com/shorts/ID`, `youtube.com/embed/ID`, variantes móveis (`m.youtube.com`) e parâmetros de query adicionais (`?t=`, `&feature=`).
  - Renderização automática de cards de mídia com design Neo-Brutalist na página `/diario` e na visualização detalhada de posts (`/post/{slug}`), utilizando a thumbnail oficial em alta resolução (`https://img.youtube.com/vi/ID/hqdefault.jpg`), overlay retrô com botão de play interativo e suporte ao Facade Pattern (carregamento sob demanda de `iframe` leve e responsivo ao clicar).
  - Componente de prévia para links convencionais (não-vídeo) através do helper `render_link_preview()`, gerando caixas de hiperlink com identificador de domínio, estilização neon e atributos de segurança sanitizados (`target="_blank" rel="noopener noreferrer"`).
  - Atualização do parser de Markdown e da sanitização do Bleach em `main.py` para permitir a tag `<iframe>` e atributos necessários para mídia de forma 100% segura contra XSS.
  - Registro de alias oficial para a rota `/diario` no FastAPI apontando para o feed principal da timeline.

### 🎮 Laboratório
* **Inclusão do emulador N64 cross-platform:**
  - Adicionado à seção do Laboratório (`/lab`) o recurso de destaque para o emulador **simple64** (anteriormente m64p), compatível com Windows, macOS e Linux, apontando para o link oficial seguro: [https://simple64.github.io/](https://simple64.github.io/).
  - Adicionada alternativa de alta fidelidade com o **Ares Emulator**, com link oficial seguro: [https://ares-emulator.github.io/](https://ares-emulator.github.io/).
  - Criado card visual Neo-Brutalist homologado no topo do Laboratório com título, badge descritivo de plataformas suportadas, resumo técnico dos núcleos Vulkan (ParaLLEl-RDP/RSP) e botões de direcionamento seguro (`rel="noopener noreferrer"`).
  - Seed automático no banco de dados SQLite (`init_db.py`) garantindo persistência e ranqueamento do simple64 entre as submissões aprovadas do terminal.
