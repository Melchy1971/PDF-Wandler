from app.parsing import find_invoice_date

def test_simple():
    d, c = find_invoice_date("Rechnungsdatum: 14.03.2024")
    assert str(d) == "2024-03-14" and c > 0.7
