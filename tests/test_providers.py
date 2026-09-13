import unittest

from solana_memecoin_research.providers import is_solana_address


class ProviderTests(unittest.TestCase):
    def test_solana_address_validation(self) -> None:
        self.assertTrue(
            is_solana_address("DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263")
        )
        self.assertFalse(
            is_solana_address("DezXAZ8z7PnrnRJjz3wXBoRgixCa6c9V2wP1pPB263")
        )
        self.assertFalse(is_solana_address("not-a-solana-address"))


if __name__ == "__main__":
    unittest.main()
