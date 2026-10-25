# Vallox Digit S

Python-kirjasto ja Home Assistant -integraatio vanhalle Vallox / Ilmava Digit S
-ilmanvaihtokoneelle, jossa on LED-seinäpaneeli. Yhteys toimii RS485-väylästä
sarjaporttisovittimen tai läpinäkyvän TCP-sillan kautta: 9600 baud, 8N1.

**Beta.** Testattu vanhalla Digit S -koneella. Uudemman Vallox MV:n WebSocket API
käyttää eri protokollaa.

## Home Assistant

1. Kopioi `custom_components/vallox_digit_s_legacy` Home Assistantin asetuskansion
   `custom_components`-hakemistoon ja käynnistä Home Assistant uudelleen.
2. Lisää **Vallox Digit S** kohdasta **Asetukset → Laitteet ja palvelut**.
3. Anna yhteysosoite, esimerkiksi `socket://vallox-gateway.local:8899`.

Vaatii Home Assistant 2026.9:n tai uudemman. Käytä yhdellä väylällä yhtä asiakasta.

Integraatio lukee neljä lämpötilaa, puhallintason ja lämpötilapyynnön.
Puhallinohjaus tukee tasoja 1–8. Aseta asennuksesi vähimmäistaso (1–8)
integraation asetuksista. Oletus on 5, ja nykyiset asetukset säilyvät. Sama
vähimmäistaso koskee kaikkia ohjaustapoja ja automaatioita. Lämpötilapyyntö käyttää koneen kahdeksaa porrasta;
≈-merkillä näkyvät Celsius-arvot ovat arvioita. Lämmityksen käyttökytkintä ja
ohituspeltiä ei ole varmistettu tälle ohjaimelle.

Suodattimen vaihtopäivä ja vaihtoväli tallentuvat Home Assistantiin. Ilmamäärä- ja
tehoarviot perustuvat asetuksiin antamiisi mittauksiin.

## Python

Kirjastoa voi käyttää myös ilman Home Assistantia. Asennus, käyttöesimerkit ja
async-rajapinta ovat [englanninkielisessä ohjeessa](README.md) ja [API-ohjeessa](docs/api.md).

[Alkuperäinen Digit SE -käyttöohje (PDF)](docs/manuals/D_se_kho.pdf) ·
[Tuetut ominaisuudet](docs/feature-comparison.md) · [Lisenssi ja lähteet](NOTICE.md)
