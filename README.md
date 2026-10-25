# Vallox Digit S → Home Assistant

Vanhan **Vallox / Ilmava Digit S:n** paikallinen Home Assistant -integraatio.
Tarkoitettu vanhalle LED-paneelille. **Ensijulkaisu on beta.**

Saat lämpötilat, puhallinsäädön, tuloilman lämpötilapyynnön ja suodatinmuistutuksen.
Ilmavirran ja tehon arviot saat syöttämällä oman koneesi arvot asetuksiin.

## Asennus

1. Lataa tämä projekti: **Code → Download ZIP**.
2. Kopioi `custom_components/vallox_digit_s_legacy` Home Assistantin
   `config/custom_components/`-kansioon ja käynnistä Home Assistant uudelleen.
3. Avaa **Asetukset → Laitteet ja palvelut → Lisää integraatio → Vallox Digit S**.
4. Valitse RS485-yhteys. Verkkosillan osoite on esimerkiksi `socket://vallox-gateway.local:8899`.

Tarvitset Home Assistant 2026.9:n tai uudemman sekä yhteensopivan RS485-sillan
(ESPHome tai läpinäkyvä TCP-silta, 9600 baud / 8N1). Käytä väylällä vain yhtä integraatiota.

## Käyttö

- Säädä puhallusta **Ilmanvaihto**-kortista. Tuettu säätöalue on 5–8.
- Valitse **Tuloilman lämpötilapyyntö**. Merkintä **≈** tarkoittaa asteikkoarviota.
- Kirjaa suodattimien vaihtopäivä ja huoltoväli. Huollon erääntymisestä voi tehdä HA-ilmoituksen.

Tämä julkaisu ei ohjaa lämmityksen käyttökytkintä tai ohituspeltiä eikä tulkitse
vahvistamattomia vikakoodeja. Se ei korvaa ilmanvaihdon säätöä tai koneen suojauksia.

[Tuetut ominaisuudet](docs/feature-comparison.md) · [Testaus ja rajaukset](docs/validation.md)

GPL-3.0. Protokollalähteet ja tekijät: [NOTICE](NOTICE.md).
