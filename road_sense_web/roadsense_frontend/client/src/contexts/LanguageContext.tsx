import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Language = "en" | "hi";

const copy = {
  en: {
    operations: "Operations control", citySignal: "City signal, live", roadSpeaking: "The road is speaking.", roadIntelligence: "Live road intelligence, organized for faster response.", overview: "Overview", live: "Live", incidents: "Incidents", routes: "Routes", dashboard: "Dashboard", liveCamera: "Live camera", cameraDescription: "Your device camera with real-time RoadSense detection", startCamera: "Start camera", stop: "Stop", reportIncident: "Report an incident", reportDescription: "Add the reporter and location details for this incident.", reporterName: "Reporter name *", email: "Email address", incidentLocation: "Incident location or road name *", address: "Building, street, or road", area: "Area or locality", city: "City", postalCode: "Postal code", landmark: "Nearby landmark", addGps: "Add GPS (optional)", gpsAttached: "GPS attached", locating: "Locating", details: "What should the response team know?", attachEvidence: "Attach photo or video", submitReport: "Submit report", sending: "Sending", pothole: "Pothole", manhole: "Manhole", crack: "Road crack", bump: "Road bump", other: "Other hazard", smsReporting: "SMS reporting", smsFormat: "Text POTHOLE | location | details", detectionMap: "Detection map", liveGps: "Live GPS",
  },
  hi: {
    operations: "संचालन नियंत्रण", citySignal: "शहर संकेत, लाइव", roadSpeaking: "सड़क बोल रही है।", roadIntelligence: "तेज़ प्रतिक्रिया के लिए व्यवस्थित लाइव सड़क जानकारी।", overview: "अवलोकन", live: "लाइव", incidents: "घटनाएं", routes: "मार्ग", dashboard: "डैशबोर्ड", liveCamera: "लाइव कैमरा", cameraDescription: "रीयल-टाइम रोडसेंस पहचान के साथ आपका डिवाइस कैमरा", startCamera: "कैमरा शुरू करें", stop: "रोकें", reportIncident: "घटना रिपोर्ट करें", reportDescription: "इस घटना के लिए रिपोर्टर और स्थान की जानकारी जोड़ें।", reporterName: "रिपोर्टर का नाम *", email: "ईमेल पता", incidentLocation: "घटना का स्थान या सड़क का नाम *", address: "भवन, गली या सड़क", area: "क्षेत्र या इलाका", city: "शहर", postalCode: "पिन कोड", landmark: "नजदीकी पहचान", addGps: "GPS जोड़ें (वैकल्पिक)", gpsAttached: "GPS जुड़ा है", locating: "स्थान खोजा जा रहा है", details: "प्रतिक्रिया टीम को क्या पता होना चाहिए?", attachEvidence: "फोटो या वीडियो जोड़ें", submitReport: "रिपोर्ट भेजें", sending: "भेजा जा रहा है", pothole: "गड्ढा", manhole: "मैनहोल", crack: "सड़क की दरार", bump: "सड़क का उभार", other: "अन्य खतरा", smsReporting: "SMS रिपोर्टिंग", smsFormat: "भेजें: POTHOLE | स्थान | जानकारी", detectionMap: "पहचान मानचित्र", liveGps: "लाइव GPS",
  },
} as const;

type CopyKey = keyof typeof copy.en;
type LanguageContextValue = { language: Language; setLanguage: (language: Language) => void; t: (key: CopyKey) => string };
const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<Language>(() => localStorage.getItem("roadsense-language") === "hi" ? "hi" : "en");
  useEffect(() => { localStorage.setItem("roadsense-language", language); document.documentElement.lang = language === "hi" ? "hi" : "en"; }, [language]);
  const value = useMemo(() => ({ language, setLanguage, t: (key: CopyKey) => copy[language][key] }), [language]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) throw new Error("useLanguage must be used inside LanguageProvider");
  return context;
}
