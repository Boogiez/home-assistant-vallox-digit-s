# Credits and licence

This project is distributed under GPL-3.0; see LICENSE.

- The NTC5K table and DIN reference airflow formula are adapted from
  [Tom-Bom-badil/home-assistant_helios-vallox](https://github.com/Tom-Bom-badil/home-assistant_helios-vallox), GPL-3.0.
- Legacy framing and speed-command behavior were compared with
  [pvainio/vallox-rs485](https://github.com/pvainio/vallox-rs485).
- Protocol mapping was checked against legacy Digit S documentation and physical
  LED-panel captures. Newer Digit SE registers are not assumed interchangeable.

Documentation consulted:
[Digit S](https://pictures.suodatinkeskus.com/Vallox%20Digit%20S.pdf) and
[contemporary SE LED panel](https://sisailmahuolto.com/wp-content/uploads/2013/09/D_se_kho.pdf).
The latter is supporting evidence, not validation of every old S register.

This is an independent community project, not an official Vallox integration.
