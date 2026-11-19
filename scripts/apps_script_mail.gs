/**
 * Momenz — Gmail Apps Script mail köprüsü
 *
 * Neden: Render free web servisleri 25/465/587 portlarını kapatıyor.
 * Bu script Google sunucularında çalışır, MailApp ile mevcut Gmail
 * hesabından mail atar ve API tarafından yalnızca HTTPS ile çağrılır.
 *
 * KURULUM
 * 1. https://script.google.com -> Yeni proje.
 * 2. Bu dosyanın tamamını Code.gs içine yapıştır.
 * 3. SECRET değerini uzun ve rastgele bir değerle değiştir:
 *      openssl rand -hex 32
 *    Aynı değeri Render'da MOMENZ_MAIL_WEBHOOK_SECRET olarak gir.
 * 4. Dağıt -> Yeni dağıtım -> Tür: Web uygulaması.
 *      Şu kullanıcı olarak yürüt: Ben
 *      Erişimi olanlar: Herkes
 * 5. Dağıtım URL'sini (/exec ile biten) Render'da
 *    MOMENZ_MAIL_WEBHOOK_URL olarak gir.
 * 6. İlk çalıştırmada Google izin ister; Gmail gönderme iznini onayla.
 *
 * NOT: Erişim "Herkes" olsa da istekler SECRET olmadan reddedilir.
 * Günlük gönderim kotası Gmail hesabına göre ~100 alıcıdır.
 */

const SECRET = 'BURAYA_64_KARAKTER_RASTGELE_SECRET';
const FROM_NAME = 'Momenz';
const MAX_SUBJECT = 200;
const MAX_BODY = 20000;

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return json({ ok: false, error: 'empty' });
    }

    const data = JSON.parse(e.postData.contents);
    if (String(data.secret || '') !== SECRET) {
      return json({ ok: false, error: 'unauthorized' });
    }

    const to = String(data.to || '').trim();
    const subject = String(data.subject || '')
      .replace(/[\r\n]+/g, ' ')
      .trim()
      .slice(0, MAX_SUBJECT);
    const body = String(data.body || '').slice(0, MAX_BODY);

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(to)) {
      return json({ ok: false, error: 'bad_to' });
    }
    if (!subject) {
      return json({ ok: false, error: 'bad_subject' });
    }
    if (MailApp.getRemainingDailyQuota() < 1) {
      return json({ ok: false, error: 'quota' });
    }

    MailApp.sendEmail({ to: to, subject: subject, body: body, name: FROM_NAME });
    return json({ ok: true, remaining: MailApp.getRemainingDailyQuota() });
  } catch (err) {
    return json({ ok: false, error: String(err) });
  }
}

function doGet() {
  return json({ ok: false, error: 'post_only' });
}

function json(value) {
  return ContentService.createTextOutput(JSON.stringify(value)).setMimeType(
    ContentService.MimeType.JSON,
  );
}
