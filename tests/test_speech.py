from alexa_ha.speech import clean_text, to_ssml


def test_markdown_is_removed():
    text = "## Status\n\n**Lights**: on\n- Kitchen: *off*\n- Hall: `on`\n\nSee [the docs](https://x.y) 😀"
    assert clean_text(text) == "Status. Lights: on. Kitchen: off. Hall: on. See the docs"


def test_snake_case_is_kept_and_numbers_listed():
    assert clean_text("1. first\n2. second") == "first. second"
    assert "light_kitchen" in clean_text("Entity light_kitchen is on")


def test_tables_become_lists():
    text = "| Room | Temp |\n|---|---|\n| Hall | 24 °C |"
    assert clean_text(text) == "Room, Temp. Hall, 24 degrees Celsius"


def test_units():
    assert clean_text("It is 24.5°C and 60% humid") == "It is 24.5 degrees Celsius and 60 percent humid"
    assert clean_text("Outside: -3 °C") == "Outside: minus 3 degrees Celsius"
    assert clean_text("Using 1.2 kW, 15 kWh today") == "Using 1.2 kilowatts, 15 kilowatt hours today"
    assert clean_text("PM2.5 is 35 µg/m³") == "PM2.5 is 35 micrograms per cubic metre"
    assert clean_text("Wind 12 km/h") == "Wind 12 kilometres per hour"
    assert clean_text("1 W") == "1 watt"
    assert clean_text("20–25°C") == "20 to 25 degrees Celsius"
    assert clean_text("20-25 °C") == "20 to 25 degrees Celsius"


def test_dates_are_left_alone():
    assert clean_text("on 2026-10-20") == "on 2026-10-20"


def test_rupees():
    assert clean_text("The bill is ₹1,250") == "The bill is 1,250 rupees"
    assert clean_text("Rs. 5 lakh") == "5 lakh rupees"
    assert clean_text("INR 300") == "300 rupees"


def test_hindi_gets_lang_tag():
    ssml = to_ssml(clean_text("Theek hai. बत्ती बंद कर दी है। Done"))
    assert ssml == '<speak>Theek hai. <lang xml:lang="hi-IN">बत्ती बंद कर दी है।</lang> Done</speak>'


def test_hindi_tag_can_be_turned_off():
    assert to_ssml("नमस्ते", hindi=False) == "<speak>नमस्ते</speak>"


def test_ssml_is_escaped():
    assert to_ssml(clean_text("Tom & Jerry <3")) == "<speak>Tom and Jerry &lt;3</speak>"


def test_long_text_is_cut_at_a_sentence():
    text = "This is one sentence. " * 200
    out = clean_text(text, max_chars=100)
    assert len(out) <= 100 and out.endswith(".")


def test_empty():
    assert clean_text("") == ""
    assert clean_text("**") == ""
