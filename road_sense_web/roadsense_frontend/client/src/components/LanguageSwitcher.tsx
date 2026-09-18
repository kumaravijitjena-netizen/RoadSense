import { Languages } from "lucide-react";
import { useLanguage } from "@/contexts/LanguageContext";

export function LanguageSwitcher() {
  const { language, setLanguage } = useLanguage();
  return <label className="language-switcher"><Languages size={15} /><select value={language} onChange={event => setLanguage(event.target.value as "en" | "hi")} aria-label="Choose language"><option value="en">English</option><option value="hi">हिंदी</option></select></label>;
}
