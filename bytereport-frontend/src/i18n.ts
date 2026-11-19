import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import ru from "./locales/ru.json";
import uz from "./locales/uz.json";
import en from "./locales/en.json";
// Copy the PDF also reads, from the same file. The Health Score's scope
// statement has to be word-for-word identical on both surfaces, so it is not
// duplicated into the locale files — it is merged in from the shared source.
import copy from "../../report-copy.json";

type Lang = "ru" | "uz" | "en";

/** Lift `{key: {ru, uz, en}}` blocks into one language's resource tree. */
function shared(lang: Lang): Record<string, Record<string, string>> {
  const out: Record<string, Record<string, string>> = {};
  for (const [section, entries] of Object.entries(copy)) {
    if (section.startsWith("_")) continue;
    out[section] = {};
    for (const [key, byLang] of Object.entries(entries as Record<string, unknown>)) {
      if (key.startsWith("_")) continue;
      const value = (byLang as Record<Lang, string>)[lang];
      if (typeof value === "string") out[section][key] = value;
    }
  }
  return out;
}

// English is the base language: this is sold to Uzbek and CIS businesses, but
// a visitor who has never chosen gets the one language the product can assume
// least wrongly. The first-visit card offers the real choice immediately.
const savedLang = localStorage.getItem("br_lang") ?? "en";

i18n.use(initReactI18next).init({
  resources: {
    ru: { translation: { ...ru, ...shared("ru") } },
    uz: { translation: { ...uz, ...shared("uz") } },
    en: { translation: { ...en, ...shared("en") } },
  },
  lng: savedLang,
  fallbackLng: "en",   // a missing key falls back to the base language, not to Russian
  interpolation: { escapeValue: false },
});

export default i18n;
