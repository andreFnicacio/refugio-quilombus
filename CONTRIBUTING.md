# 🤝 Guia de Contribuição // O Refúgio

Obrigado por querer contribuir com **O Refúgio**! Este é um projeto *open source* voltado para desenvolvedores e entusiastas da web independente, priorizando arquitetura monolítica sustentável, FinOps e estética Neo-Brutalist.

---

## 🧭 Princípios de Desenvolvimento

1. **FinOps & Leveza**: O projeto foi desenhado para rodar em uma VPS modesta de 1 vCPU e 1GB de RAM gastando menos de 100MB. Evite dependências que adicionem peso excessivo ao runtime.
2. **Segurança em Camadas**:
   - Todo Markdown ou conteúdo de terceiros renderizado em tela DEVE passar por sanitização via `bleach`.
   - Uploads de imagem devem obrigatoriamente validar a extensão e os **Magic Bytes** dos arquivos.
   - Rotas de ação (likes, comentários, login) devem ser protegidas por rate limiting com `slowapi`.
3. **Estética Neo-Brutalism**: Mantenha o padrão visual com sombras duras (`4px 4px 0 #000`), bordas de 3px e a paleta de cores definida em `static/css/style.css`.
4. **Zero Bloat de Frontend**: Usamos apenas Jinja2 server-side rendering e Vanilla JavaScript limpo.

---

## 🛠️ Como Configurar o Ambiente

1. Clone o seu fork do repositório:
   ```bash
   git clone https://github.com/SEU_USUARIO/refugio-quilombus.git
   cd refugio-quilombus
   ```
2. Execute o setup automatizado via Makefile:
   ```bash
   make setup
   ```
   *Nota: O Makefile identifica se você possui o gerenciador `uv` instalado e o utiliza automaticamente para acelerar a instalação.*

3. Crie os dados de demonstração e o banco SQLite (WAL mode):
   ```bash
   make seed
   ```

4. Suba o servidor com hot-reload:
   ```bash
   make run
   ```

---

## 🧪 Como Testar

Nenhum código é mergeado sem cobertura de testes. Para rodar a bateria automatizada completa:

```bash
make test
```

Caso queira rodar um teste específico:
```bash
.venv/bin/pytest -k "test_magic_bytes" -v
```

Garanta que todos os 21 testes (ou novos testes que você criar) estejam 100% verdes antes de abrir seu Pull Request.

---

## 📋 Padrão de Commits

Adotamos a especificação de [Conventional Commits](https://www.conventionalcommits.org/pt-br/v1.0.0/):

- `feat:` Uma nova funcionalidade ou recurso para o usuário
- `fix:` Correção de um bug ou comportamento incorreto
- `refactor:` Refatoração de código sem alteração funcional
- `test:` Adição ou correção de testes automatizados
- `docs:` Alterações em documentação ou comentários
- `chore:` Atualização de dependências, builds ou scripts de manutenção

Exemplo:
```bash
git commit -m "feat(lab): add github stars preview badge"
git commit -m "fix(security): prevent stored XSS on author url field"
```

---

## 🚀 Submetendo um Pull Request (PR)

1. Crie uma branch com nome descritivo a partir da `main`:
   ```bash
   git checkout -b feat/minha-melhoria
   ```
2. Escreva o código e os testes correspondentes.
3. Certifique-se de que a suíte `make test` está passando.
4. Execute `make clean` para remover artefatos temporários e caches.
5. Faça o push para o seu fork e abra o Pull Request detalhando as mudanças e a motivação técnica.
