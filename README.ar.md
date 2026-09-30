<p align="center">
  <img src="assets/logo.png" alt="شعار Byte Balance Technology" width="480">
</p>

<div dir="rtl">

# ByteGuard

[English](README.md)

ByteGuard ينصّب سيرفر WireGuard على جهازك بأمر واحد، ويتيح لك إدارة الأجهزة من صفحة ويب، ويعيد كل الإعدادات من ملف نسخة احتياطية واحد بعد إعادة تثبيت السيرفر.

<p align="center">
  <img src="assets/screenshots/devices-ar.png" alt="واجهة الويب: الأجهزة وحالة اتصالها واستهلاكها" width="620">
</p>

## التنصيب

على سيرفر Ubuntu 22.04 أو أحدث، أو Debian 12 أو أحدث:

<div dir="ltr">

```bash
curl -fsSL https://bytebalancetech.com/byteguard.sh -o byteguard.sh
sudo bash byteguard.sh
```

</div>

البرنامج مضمّن داخل ملف التنصيب كنص مقروء، فتستطيع قراءته قبل تشغيله، ومع كل إصدار ملف `byteguard.sh.sha256` للتحقق منه.

## ماذا يفعل

- **إعداد موجّه:** يكتشف كرت الشبكة المتصل بالإنترنت وعنوان السيرفر العام ويطلب تأكيدهما، ثم يسأل عن المنفذ (الافتراضي `51820`).
- **كل ترافيك الأجهزة يمر عبر السيرفر**، مع `PersistentKeepalive = 25` و `MTU = 1420`.
- **إدارة الأجهزة:** إضافة وحذف وتعطيل مؤقت، وعرض رمز QR في أي وقت، من الطرفية أو من الواجهة.
- **نسخة احتياطية بعد كل تعديل** دون أي ضغطة. النسخة ملف واحد قابل للتشغيل: شغّله على سيرفر جديد فيعود الـ VPN بنفس المفاتيح، وتتصل الأجهزة دون إعدادات جديدة. تُحفظ في `/var/backups/byteguard/`، ويمكن إرسالها إلى محادثة Telegram ورفعها إلى تخزين متوافق مع S3 مثل Cloudflare R2.
- **واجهة ويب بالعربية والإنجليزية**، لا تعمل إلا من داخل الـ VPN.
- **اختيارياً:** الواجهة على دومينك عبر Cloudflare Tunnel دون فتح أي منفذ. ينشئ ByteGuard نفقاً خاصاً به ولا يلمس أي نفق موجود على السيرفر.
- **يحترم الجدار الناري الموجود:** يضيف قواعد ufw أو iptables دون مسح أي شيء، وإزالة التنصيب تحذف ما أضافه فقط.

كل شيء يعمل على سيرفرك وبحساباتك أنت. ByteGuard لا يملك خدمة مستضافة ولا يجمع أي بيانات.

## الأوامر

بعد التنصيب يفتح `sudo byteguard` قائمة، ونفس الإجراءات متاحة كأوامر:

| الأمر | ماذا يفعل |
|---|---|
| `sudo byteguard add NAME` | إضافة جهاز وعرض إعداداته ورمز QR |
| `sudo byteguard show NAME` | عرض إعدادات جهاز ورمز QR مرة أخرى |
| `sudo byteguard list` | قائمة الأجهزة |
| `sudo byteguard status` | من المتصل واستهلاك كل جهاز |
| `sudo byteguard disable NAME` | منع جهاز من الاتصال دون حذفه (`enable` يعيده) |
| `sudo byteguard remove NAME` | حذف جهاز |
| `sudo byteguard port NUMBER` | نقل الـ VPN إلى منفذ آخر؛ كل جهاز يحتاج إعداداته من جديد |
| `sudo byteguard ui setup` | تشغيل الواجهة وتعيين كلمة سرها (`ui off` يوقفها) |
| `sudo byteguard ui tunnel` | الواجهة على دومينك عبر Cloudflare (`--off` يوقفها) |
| `sudo byteguard backup` | نسخة احتياطية الآن |
| `sudo byteguard backup telegram` | إرسال كل نسخة إلى Telegram عبر bot خاص بك |
| `sudo byteguard backup s3` | رفع كل نسخة إلى R2 أو أي تخزين متوافق مع S3 |
| `sudo byteguard uninstall` | إزالة الـ VPN ومفاتيحه و ByteGuard |

## الواجهة

`sudo byteguard ui setup` يطلب كلمة سر ويشغّل الواجهة على عنوان السيرفر داخل الـ VPN، مثل `http://10.66.66.1:51821`. افتحها من جهاز متصل بالـ VPN؛ من أي مكان آخر لا يجيب العنوان. ثماني كلمات سر خاطئة من نفس العنوان تقفل الدخول منه خمس دقائق، دون أن تؤثر على غيره.

مع `sudo byteguard ui tunnel` تصبح الواجهة على عنوان مثل `https://vpn.example.com`. يحتاج ذلك دوميناً في حسابك على Cloudflare (الخطة المجانية تكفي). بعد تفعيلها يصل أي شخص يعرف العنوان إلى صفحة الدخول، فاستخدم كلمة سر قوية، ويُفضّل وضع Cloudflare Access أمامها.

## الاسترجاع

انسخ ملف النسخة الاحتياطية إلى سيرفر جديد وشغّله:

<div dir="ltr">

```bash
sudo bash byteguard-backup-NAME.sh
```

</div>

تتصل الأجهزة وحدها إذا كان للسيرفر الجديد نفس العنوان العام. إذا تغيّر العنوان، مرّر `--endpoint NEW_ADDRESS`، وعندها يحتاج كل جهاز إعداداته من جديد.

**النسخة الاحتياطية غير مشفّرة.** تحتوي مفتاح السيرفر ومفاتيح كل الأجهزة ورموز Telegram والتخزين. من يحصل عليها يستطيع الاتصال بالـ VPN، فاحفظها هي والمحادثة والـ bucket في مكان خاص. التفاصيل في [SECURITY.md](SECURITY.md).

## الدعم

إذا كان المشروع مفيداً لك، يمكنك دعم تطويره عبر Binance Pay: افتح تطبيق Binance وامسح الرمز أدناه، أو ابحث عن الاسم **Kinan125**.

<p align="center">
  <img src="assets/binance.jpg" alt="رمز Binance Pay - Kinan125" width="280">
</p>

## الترخيص

MIT، انظر [LICENSE](LICENSE).

WireGuard علامة تجارية مسجّلة لـ Jason A. Donenfeld. ByteGuard مشروع مستقل وغير تابع لمشروع WireGuard أو معتمد منه.

</div>
