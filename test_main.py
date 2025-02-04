import unittest
from main import detect_date, analyze_text

class TestMainFunctions(unittest.TestCase):

    def test_detect_date(self):
        self.assertEqual(detect_date("2024-02-03"), "2024-02-03")
        self.assertEqual(detect_date("03.02.2024"), "2024-02-03")
        self.assertEqual(detect_date("02/03/2024"), "2024-02-03")
        self.assertEqual(detect_date("2024/02/03"), "2024-02-03")
        self.assertEqual(detect_date("3. Feb. 2024"), "2024-02-03")
        self.assertEqual(detect_date("3 February 2024"), "2024-02-03")
        self.assertEqual(detect_date("20240203"), "2024-02-03")
        self.assertEqual(detect_date("Rechnungsdatum 17 Juli 2018"), "2018-07-17")
        self.assertEqual(detect_date("Lieferdatum 17 Juli 2018"), "2018-07-17")
        self.assertIsNone(detect_date("Invalid date"))

    def test_analyze_text(self):
        text = "Rechnung Nr.: 12345\nFirma GmbH\nDatum: 03.02.2024"
        result = analyze_text(text)
        self.assertEqual(result["company_name"], "Firma GmbH")
        self.assertEqual(result["date"], "2024-02-03")
        self.assertEqual(result["number"], "12345")

        text = "Rechnungsnummer: ABC-123-XYZ\nCompany AG\nDate: 2024-02-03"
        result = analyze_text(text)
        self.assertEqual(result["company_name"], "Company AG")
        self.assertEqual(result["date"], "2024-02-03")
        self.assertEqual(result["number"], "ABC-123-XYZ")

if __name__ == '__main__':
    unittest.main()
