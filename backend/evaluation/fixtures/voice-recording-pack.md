# Human voice benchmark recording pack

This pack contains 60 distinct questions whose source prompts were selected from the indexed MSMARCO-XI validation corpus. Record the six sessions below; do not record the numbers or identifiers.

The machine-readable plan is in `voice-recording-plan.csv`. Recorded audio is private evaluation data and must be saved under `backend/evaluation/private`, not committed with this public prompt pack.

## Recording rules

1. Use the exact session filename shown below. M4A or WAV is acceptable.
2. Start with approximately two seconds of silence.
3. Speak only each displayed question. Do not say “question one”, the prompt ID, or the language label.
4. Leave three seconds of silence after every question so the recording can be segmented reliably.
5. Speak naturally. Do not rush prompts labelled long; they should normally last at least three seconds.
6. If you make a mistake, pause for three seconds and repeat that entire question. Keep a short note of the prompt number that was repeated.
7. End with approximately two seconds of silence.
8. Keep the microphone roughly 20–30 cm from your mouth and do not change devices within a session.
9. For clean sessions, use a quiet room. For noisy sessions, use mild steady background noise such as a fan or distant traffic. The speech must remain easy to understand; do not use music or another speaking voice.
10. Read Roman Hindi exactly as written in the `hi-en` sessions. Punctuation does not need to be spoken.

## Session 01 — Hindi, clean

Save as `session-01-hi-clean.m4a`.

1. प्रोटिओमिक्स क्या है?
2. एकीकृत बहु-विषयक देखभाल क्या है?
3. ऊर्ध्वाधर विभेदन क्या है?
4. परिवार प्रबंधन क्या है?
5. पीटर्सबर्ग, इंडियाना किस समय क्षेत्र में है?
6. माओ त्से-तुंग की मृत्यु किस वर्ष हुई थी?
7. चींटियों को नष्ट करने का सबसे अच्छा समय कब होता है?
8. तत्वों और यौगिकों को शुद्ध पदार्थ क्यों माना जाता है?
9. प्रोटॉन पंप अवरोधक कैसे काम करते हैं?
10. क्या बराक ओबामा फिर से अमेरिकी राष्ट्रपति पद के लिए चुनाव लड़ सकते हैं?

## Session 02 — English, clean

Save as `session-02-en-clean.m4a`.

1. What type of malware is XcodeGhost?
2. What kind of volcano is Chato?
3. What is a net gain or loss?
4. What is pododermatitis?
5. What is the Lancefield method?
6. Which NHL teams did Jaromir Jagr play for?
7. Which judicial district is Scott County, Minnesota, in?
8. When was the De Lôme Letter published?
9. In what year was Cathy Dennis's song Touch Me, Hold Me released?
10. What is the mass ratio of hydrogen to oxygen when they form water?

## Session 03 — Hindi-English code-mix, clean

Save as `session-03-hi-en-clean.m4a`.

1. Architecture mein loggia kya hoti hai?
2. Medical term purulent ka meaning kya hai?
3. Tungsten element ka proton count kya hai?
4. Devil's advocate phrase ka meaning samjhao.
5. Allocating word ki definition batao.
6. America ka first federally funded highway kaunsa tha?
7. Chile country ki official administrative language kya hai?
8. Riboflavin kaunsa vitamin hai aur body ko kyun chahiye?
9. Xenotransplantation mein cells tissues ya organs kahan transfer hote hain?
10. Third-party custody mein child ki custody kisko milti hai?

## Session 04 — Hindi, mildly noisy

Save as `session-04-hi-noisy.m4a`.

1. बी.आर.एल. किस देश की मुद्रा है?
2. नामीबिया की आधिकारिक मुद्रा क्या है?
3. हिस्पैनियोला किस प्रकार का द्वीप है?
4. लोकप्रिय संस्कृति के कुछ उदाहरण क्या हैं?
5. एस्टर-सी किससे बनाया जाता है?
6. औसत पैदल चलने की गति क्या होती है?
7. शांग राजवंश की सबसे महत्वपूर्ण कला कौन-सी थी?
8. गिटार पिक की मानक मोटाई क्या होती है?
9. बोस्टन सेल्टिक्स ने कितनी एन.बी.ए. चैंपियनशिप जीती हैं?
10. मोह्स पैमाने पर सोने की कठोरता कितनी होती है?

## Session 05 — English, mildly noisy

Save as `session-05-en-noisy.m4a`.

1. What is included in a development agreement?
2. What is the definition of reconstitute?
3. What is D-pantothenol?
4. Which materials are popular for kitchen countertops?
5. At what temperature does petrol freeze?
6. At what speed should annular cutters be used?
7. What type of business was Lehman Brothers?
8. Which is longer, a California king or a standard king bed?
9. What does Pascal's law mean in simple terms?
10. How can a checking account affect your credit score?

## Session 06 — Hindi-English code-mix, mildly noisy

Save as `session-06-hi-en-noisy.m4a`.

1. Aristocracy ka simple meaning kya hai?
2. Hanker word ka meaning kya hai?
3. Succulent plants ka meaning kya hai?
4. Grout ki definition kya hai?
5. Hematemesis ka medical meaning kya hai?
6. Diencephalic Syndrome kis type ka disorder hai aur kis wajah se hota hai?
7. Pascal's law simple terms mein kya kehta hai?
8. Cell ki primary energy-carrying molecule kaunsi hai?
9. Biology mein blotting ka matlab kya hai?
10. Sled pull karne ke liye kis type ke dogs use hote hain?

## Where to place the recordings

Create this local directory and copy the six recordings into it:

```text
C:\RAG\backend\evaluation\private\recording-sessions\
```

The expected files are:

```text
session-01-hi-clean.m4a
session-02-en-clean.m4a
session-03-hi-en-clean.m4a
session-04-hi-noisy.m4a
session-05-en-noisy.m4a
session-06-hi-en-noisy.m4a
```

Do not convert or edit the originals. Segmentation, mistake handling, trimming, PCM conversion, transcript verification, and benchmark-manifest generation will be performed after the six source recordings are supplied.
