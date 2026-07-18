<div dir="rtl">

# النشر

النشرُ هنا **موثوقٌ عبر OIDC**: لا توكن ولا كلمة سرّ في أيّ مكان. تُصدر
GitHub رمزاً قصير العمر لهذا المستودع ولملف سير عملٍ بعينه، وتتحقق منه
PyPI مباشرةً. فليس ثمّ سرٌّ يُخزَّن، ولا سرٌّ يُسرَّب، ولا سرٌّ يُنسى
فينتهي صلاحيّته يوم تحتاجه.

---

## ⚠️ اقرأ هذا قبل كل شيء

> **الناشرُ المعلَّق لا يحجز الاسم.**
>
> PyPI تقول بالحرف: *«Configuring a "pending" publisher for a project name
> does not reserve that name. Until the project is created, any other user
> may create it.»*
>
> فبين إعداد الناشر وأوّل رفعةٍ **نافذةٌ مفتوحة** لأيّ أحد. اختصِرها:
> أعِدّ الناشر، ثم انشر إصداراً فوراً — ولو `0.0.1` فارغاً لحجز الاسم.

> **PyPI لا تقبل رفع نسخةٍ مرّتين. أبداً.**
>
> حذفُ نسخةٍ لا يُحرّر رقمها. فخطأٌ في الرقم لا يُصلَح — يُهجَر ويُرفع
> رقمٌ جديد. ولهذا في `publish.yml` مهمّة `guard` تسبق كل شيء وتتحقق من
> الرقم قبل أن يُبنى شيء.

---

## ١) إعداد الناشر المعلَّق على PyPI

في صفحة *Publishing → Add a new pending publisher*، اختر **GitHub** واملأ:

| الحقل | القيمة |
|---|---|
| **PyPI Project Name** | `arafix` — أو الاسم البديل، انظر «التسمية» في الـ README |
| **Owner** | `bio-colab` |
| **Repository name** | `arafix` |
| **Workflow name** | `publish.yml` — **الاسم بالحرف، وهو جزءٌ من العقد** |
| **Environment name** | `pypi` |

ثم كرّر العملية على [test.pypi.org](https://test.pypi.org) بنفس القيم مع
`Environment name` = `testpypi`. حسابا الموقعين منفصلان.

**Workflow name خانةٌ حسّاسة**: تغييرُ اسم الملف في المستودع يكسر النشر
حتى تُحدَّث الإعدادات هناك.

## ٢) إعداد البيئتين على GitHub

*Settings → Environments → New environment*، أنشئ `pypi` و`testpypi`.

وعلى `pypi` خاصّةً، فعّل **Required reviewers** وضع نفسك. وهذا ليس
احتياطاً زائداً: بدونه، **أيُّ أحدٍ له صلاحيةُ الدفع إلى المستودع يملك
صلاحيةَ النشر باسمك على PyPI**. والبيئةُ تفصل الصلاحيتين، وهي السبب الذي
تُوصي PyPI بها.

## ٣) جرّب على TestPyPI أوّلاً

*Actions → publish → Run workflow → target: `testpypi`*

ثم تحقق أن ما رُفع يُثبَّت ويعمل فعلاً:

</div>

```bash
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ arafix
arafix --version
arafix text "$(python -c 'print("\ufee3\ufeae\ufea3\ufe92\ufe8e")')"   # ← مرحبا
```

<div dir="rtl">

`--extra-index-url` ضروريّ: تبعيّاتك (PyMuPDF وغيرها) ليست على TestPyPI.

## ٤) الإصدار الحقيقيّ

</div>

```bash
# ١. ارفع الرقم في موضعين — والحارس يتحقق من تطابقهما
#    pyproject.toml:  version = "0.7.0"
#    src/arafix/__init__.py:  __version__ = "0.7.0"

# ٢. اكتب مدخل CHANGELOG.md بعنوان "## 0.7.0" — والحارس يتحقق من وجوده

# ٣. ادفع، ثم أنشئ إصداراً بوسمٍ مطابق
git tag v0.7.0 && git push origin main --tags
gh release create v0.7.0 --title "0.7.0" --notes-file <(sed -n '/^## 0.7.0/,/^## /p' CHANGELOG.md | head -n -1)
```

<div dir="rtl">

ثم وافق على البيئة `pypi` في تبويب Actions. والنشرُ يجري تلقائياً.

## ما يفعله الحارس قبل أن يُبنى شيء

`publish.yml → guard` يرفض الإصدار إن:

1. **الوسم لا يطابق `__version__`** — رفعُ رقمٍ خاطئ لا يُصلَح.
2. **النسخة منشورةٌ سلفاً على PyPI** — يسأل الـ API قبل أن يحاول.
3. **`CHANGELOG.md` لا يذكرها** — لا نُصدر إصداراً لا يقول للناس ما تغيّر.

ثم تمرّ الاختبارات على 3.9 و3.13 قبل البناء، ويمرّ `twine check --strict`
بعده. فإن سقط شيءٌ من ذلك، لم يُرفع شيء.

## قائمةُ ما قبل أوّل نشر

- [ ] **حُسم الاسم** — الناشرُ المعلَّق لا يحجزه
- [ ] `bio-colab/arafix` موجودٌ وعامّ على GitHub
- [ ] بيئتا `pypi` و`testpypi` منشأتان، والأولى بموافقةٍ يدوية
- [ ] ناشرٌ معلَّق على PyPI و TestPyPI
- [ ] `ci.yml` أخضر على 3.9 → 3.13
- [ ] جُرّب على TestPyPI و`pip install` منه نجح
- [ ] `README` يُعرَض سليماً على TestPyPI (وهو أوّل ما يراه الناس)

</div>
