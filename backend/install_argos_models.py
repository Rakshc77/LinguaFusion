import argostranslate.package

LANGUAGE_PAIRS = [
    ("en", "de"),
    ("de", "en"),
    ("en", "es"),
    ("es", "en"),
    ("en", "hi"),
    ("hi", "en"),
]

argostranslate.package.update_package_index()
available_packages = argostranslate.package.get_available_packages()

for source, target in LANGUAGE_PAIRS:
    print(f"Installing {source} -> {target}")

    package = next(
        p for p in available_packages
        if p.from_code == source and p.to_code == target
    )

    package_path = package.download()
    argostranslate.package.install_from_path(package_path)

print("All selected Argos models installed.")