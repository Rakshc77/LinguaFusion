import argostranslate.translate

def translate(text, source_lang, target_lang):
    installed_languages = argostranslate.translate.get_installed_languages()

    source = next(lang for lang in installed_languages if lang.code == source_lang)
    target = next(lang for lang in installed_languages if lang.code == target_lang)

    translation = source.get_translation(target)
    return translation.translate(text)


print("EN -> DE:")
print(translate("Hello, how are you today?", "en", "de"))

print("DE -> EN:")
print(translate("Hallo, wie geht es dir heute?", "de", "en"))

print("EN -> ES:")
print(translate("I want to build an offline translator app.", "en", "es"))