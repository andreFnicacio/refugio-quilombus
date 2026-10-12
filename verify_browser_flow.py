import sys
from fastapi.testclient import TestClient
from main import app
from database import SessionLocal
from models import PushSubscription, PushLog
from config import settings

print("==================================================")
print("TESTE COMPLETO DE INTERFACE E CICLO DE VIDA DO WEB PUSH")
print("==================================================")

client = TestClient(app)

# 1. Teste da Home e Elementos do Navegador
res_home = client.get("/")
assert res_home.status_code == 200, f"Erro na home: {res_home.status_code}"
html_home = res_home.text

assert 'id="push-consent-modal"' in html_home, "Modal de consentimento nao encontrado no HTML!"
assert 'id="push-consent-accept"' in html_home, "Botao [SIM, ATIVAR] nao encontrado no modal!"
assert 'id="push-consent-decline"' in html_home, "Botao [NAO] nao encontrado no modal!"
assert '/static/js/notifications.js' in html_home, "Script notifications.js nao importado no base.html!"
print("[OK] Elementos da interface da Home validados (modal neo-brutalista, scripts).")

# 2. Teste do Service Worker e Escopo Raiz
res_sw = client.get("/sw.js")
assert res_sw.status_code == 200, f"Erro ao acessar /sw.js: {res_sw.status_code}"
assert "notificationclick" in res_sw.text, "Evento notificationclick ausente no Service Worker!"
assert "push" in res_sw.text, "Evento push ausente no Service Worker!"
assert res_sw.headers.get("Service-Worker-Allowed") == "/", "Cabecalho Service-Worker-Allowed ausente!"
print("[OK] Service Worker /sw.js acessivel com escopo raiz e eventos ativos.")

# 3. Teste da Chave Publica VAPID
res_key = client.get("/api/push/vapid-public-key")
assert res_key.status_code == 200, "Erro ao obter chave VAPID!"
pub_key = res_key.json().get("public_key")
assert pub_key and pub_key.startswith("B"), f"Chave publica invalida: {pub_key}"
print(f"[OK] Chave VAPID obtida com sucesso: {pub_key[:25]}...")

# 4. Simulacao de Inscricao do Navegador (Browser Client)
fake_endpoint = "https://fcm.googleapis.com/fcm/send/fake-browser-token-999"
payload_sub = {
    "endpoint": fake_endpoint,
    "p256dh": "BDUs5Y7v_tZvenSJQEajxQFaIBR9HIVtmYyzLzVoHs2NcS4ZiVU_eqI9acM35KugL122my-BGeqld8MW2L_3N4E",
    "auth": "tBHItJI5svbpez7KI4CCXg",
    "user_agent": "Google Chrome / Mac OS X 10_15_7"
}
res_sub = client.post("/api/push/subscribe", json=payload_sub)
assert res_sub.status_code == 200, f"Erro ao registrar inscricao: {res_sub.text}"
print("[OK] Inscricao do leitor registrada com sucesso no banco de dados.")

# 5. Login Administrativo
res_login = client.post(
    "/login",
    data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    follow_redirects=False
)
assert res_login.status_code in (302, 303), "Falha no login do admin!"
admin_cookie = {settings.SESSION_COOKIE_NAME: res_login.cookies.get(settings.SESSION_COOKIE_NAME)}
print("[OK] Login administrativo autenticado.")

# 6. Verificacao da Aba Web Push no Painel Admin
res_admin = client.get("/admin?tab=push", cookies=admin_cookie)
assert res_admin.status_code == 200, f"Erro ao acessar /admin: {res_admin.status_code}"
html_admin = res_admin.text

assert "Inscritos Push" in html_admin, "Card de inscritos ausente no admin!"
assert "STATUS DO PROTOCOLO WEB PUSH NATIVO" in html_admin, "Secao de status VAPID ausente!"
assert "DISPARO MANUAL OU TESTE" in html_admin, "Formulario de disparo manual ausente!"
assert "RESUMO DIARIO DO RADAR" in html_admin, "Secao de resumo do Radar ausente!"
assert "HISTORICO DE DISPAROS PUSH" in html_admin, "Tabela de historico ausente!"
print("[OK] Painel administrativo /admin?tab=push renderizado com todas as secoes.")

# 7. Disparo de Notificacao de Teste pelo Admin
res_broadcast = client.post(
    "/admin/push/broadcast",
    data={
        "title": "Notificacao de Teste via Terminal",
        "body": "Validacao completa do fluxo de Web Push nativo.",
        "target_url": "/diario"
    },
    cookies=admin_cookie,
    follow_redirects=False
)
assert res_broadcast.status_code in (302, 303), "Erro no envio manual do admin!"
print("[OK] Disparo manual executado via formulario administrativo.")

# 8. Verificacao no Banco de Dados
db = SessionLocal()
sub_count = db.query(PushSubscription).count()
last_log = db.query(PushLog).order_by(PushLog.sent_at.desc()).first()
assert sub_count >= 1, "Inscrito nao encontrado no banco!"
assert last_log is not None, "Log de push nao registrado no banco!"
print(f"[OK] Banco SQLite validado: {sub_count} inscritos ativos | Ultimo log: '{last_log.title}'.")

# Limpeza do mock de teste
db.query(PushSubscription).filter(PushSubscription.endpoint == fake_endpoint).delete()
db.commit()
db.close()

print("==================================================")
print("TODOS OS TESTES DE NAVEGADOR E FLUXO PASSARAM COM SUCESSO!")
print("==================================================")
