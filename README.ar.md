<p align="center">
  <img src="assets/logo.png" alt="شعار Byte Balance Technology" width="480">
</p>

<div dir="rtl">

# ByteGuard

[English](README.md)

ByteGuard ينصّب خادم WireGuard بأمر واحد على خادمك، ويُدير أجهزتك من صفحة ويب، ويستعيد إعداداتك كاملة من ملف نسخة احتياطية واحد بعد إعادة تثبيت الخادم.

<p align="center">
  <img src="assets/screenshots/devices-ar.png" alt="واجهة الويب: الأجهزة وحالة اتصالها واستهلاكها" width="620">
</p>

## التنصيب

على خادم يعمل بنظام Ubuntu 22.04 أو أحدث، أو Debian 12 أو أحدث:

<div dir="ltr">

```bash
curl -fsSL https://bytebalancetech.com/byteguard.sh -o byteguard.sh
sudo bash byteguard.sh
```

</div>

يحوّل هذا العنوان إلى آخر إصدار على GitHub. لتحميل النسخة مباشرة من GitHub:

<div dir="ltr">

```bash
curl -fsSL https://github.com/kenanwahbeh/ByteGuard/releases/latest/download/byteguard.sh -o byteguard.sh
```

</div>

للتحقق من الملف قبل تشغيله قارنه ببصمة SHA-256 المنشورة مع الإصدار:

<div dir="ltr">

```bash
curl -fsSLO https://github.com/kenanwahbeh/ByteGuard/releases/latest/download/byteguard.sh.sha256
sha256sum -c byteguard.sh.sha256
```

</div>

البرنامج مضمّن داخل ملف التنصيب نصاً مقروءاً، فاقرأه قبل تشغيله إن أردت.

## ما نقدّمه

- **إعداد موجّه:** يكتشف البرنامج بطاقة الشبكة وعنوان الخادم العام، ويطلب تأكيدهما والمنفذ (الافتراضي `51820`).
- **كل ترافيك الأجهزة يمرّ عبر الخادم**، مع `PersistentKeepalive = 25` و `MTU = 1420`.
- **إدارة الأجهزة:** أضف أجهزة وأزلها وعطّلها مؤقتاً، واعرض رمز QR لأي جهاز في أي وقت من الطرفية أو الواجهة.
- **نسخة احتياطية بعد كل تعديل** تلقائياً. النسخة ملف واحد يكفي تشغيله على خادم جديد ليعود كل شيء بالمفاتيح نفسها، وتتصل الأجهزة دون إعدادات جديدة. يحفظ البرنامج النسخة في `/var/backups/byteguard/`، ويرسلها إلى Telegram ويرفعها إلى S3 أو Cloudflare R2 حسب اختيارك.
- **واجهة ويب بالعربية والإنجليزية** تعمل من داخل الشبكة الافتراضية فقط.
- **اختيارياً:** الواجهة على نطاقك عبر Cloudflare Tunnel دون فتح أي منفذ. يُنشئ البرنامج نفقاً خاصاً ولا يمسّ أي نفق موجود.
- **احترام الجدار الناري:** يضيف البرنامج قواعد ufw أو iptables دون حذف قواعد موجودة، وعند الإزالة يحذف ما أضافه فقط.

كل شيء يعمل على خادمك وحسابك. البرنامج لا يجمع بيانات، والمفاتيح والأجهزة لا تغادر إلا إلى وجهات النسخ الاحتياطي التي اخترتها.

## الأوامر

بعد التنصيب يفتح الأمر `sudo byteguard` قائمةً، والإجراءات نفسها متاحة أوامرَ مستقلة:

| الأمر | الوظيفة |
|---|---|
| `sudo byteguard add NAME` | إضافة جهاز وعرض إعداداته ورمز QR |
| `sudo byteguard show NAME` | عرض إعدادات جهاز ورمز QR مرة أخرى |
| `sudo byteguard list` | قائمة الأجهزة |
| `sudo byteguard status` | الأجهزة المتصلة واستهلاك كل جهاز |
| `sudo byteguard disable NAME` | منع جهاز من الاتصال دون حذفه (`enable` يعيده) |
| `sudo byteguard remove NAME` | حذف جهاز |
| `sudo byteguard port NUMBER` | نقل الشبكة إلى منفذ آخر، ويحتاج كل جهاز بعدها إلى إعداداته من جديد |
| `sudo byteguard ui setup` | تشغيل الواجهة وتعيين كلمة مرورها (`ui off` يوقفها) |
| `sudo byteguard ui tunnel` | الواجهة على نطاقكم عبر Cloudflare (`--off` يوقفها) |
| `sudo byteguard backup` | نسخة احتياطية فورية |
| `sudo byteguard backup telegram` | إرسال كل نسخة إلى Telegram عبر بوت خاص بكم |
| `sudo byteguard backup s3` | رفع كل نسخة إلى R2 أو أي تخزين متوافق مع S3 |
| `sudo byteguard uninstall` | إزالة الشبكة ومفاتيحها و ByteGuard |

## الواجهة

شغّل `sudo byteguard ui setup` لتعيين كلمة مرور وتشغيل الواجهة على عنوان الخادم داخل الشبكة، مثل `http://10.66.66.1:51821`. الواجهة لا تُفتح إلا من جهاز متصل بالشبكة. إذا أُدخلت ثماني كلمات مرور خاطئة من عنوان واحد يُقفل الدخول منه خمس دقائق دون أن يتأثر غيره.

لتغيير كلمة المرور استخدم «تغيير كلمة المرور» أسفل الصفحة. تُطلب كلمة المرور الحالية، وتُحتسب المحاولات الخاطئة فيها كمحاولات الدخول الخاطئة، وتُغلق بعد التغيير كل الجلسات المفتوحة على الأجهزة الأخرى. إذا نُسيت كلمة المرور شغّل `sudo byteguard ui setup` على الخادم لتعيين كلمة جديدة، وتُغلق عندها كل الجلسات.

شغّل `sudo byteguard ui tunnel` لنشر الواجهة على عنوان مثل `https://vpn.example.com` عبر Cloudflare Tunnel. يتطلب نطاقاً في حسابك على Cloudflare (الخطة المجانية تكفي). بعد التفعيل يستطيع كل من يعرف العنوان الوصول إلى صفحة الدخول، فاستخدم كلمة مرور قوية، وفكّر في وضع Cloudflare Access أمامها.

## الاستعادة

لاستعادة الإعدادات انسخ ملف النسخة الاحتياطية إلى خادم جديد وشغّله:

<div dir="ltr">

```bash
sudo bash byteguard-backup-NAME.sh
```

</div>

تتصل الأجهزة تلقائياً إذا احتفظ الخادم الجديد بالعنوان نفسه. إذا تغيّر العنوان أضف `--endpoint NEW_ADDRESS` إلى أمر التشغيل، وعندها يحتاج كل جهاز إلى إعداداته من جديد.

**النسخة الاحتياطية غير مشفّرة.** تحتوي مفتاح الخادم ومفاتيح كل الأجهزة ورموز Telegram والتخزين. من يحصل عليها يستطيع الاتصال بالشبكة، فاحفظها والمحادثة والحاوية في مكان آمن. التفاصيل في [SECURITY.md](SECURITY.md).

## الدعم

إن وجدت المشروع مفيداً ادعم تطويره عبر Binance Pay: امسح الرمز أدناه من تطبيق Binance أو ابحث عن **Kinan125**.

<p align="center">
  <img src="assets/binance.jpg" alt="رمز Binance Pay - Kinan125" width="280">
</p>

## الترخيص

MIT، والتفاصيل في ملف [LICENSE](LICENSE).

WireGuard علامة تجارية مسجّلة لـ Jason A. Donenfeld، ومشروعنا ByteGuard مستقل، غير تابع لمشروع WireGuard ولا معتمد منه.

</div>
