from app.erpnext_client import ERPNextClient


OPPORTUNITIES = [
    "CRM-OPP-2026-00001",
    "CRM-OPP-2026-00002",
    "CRM-OPP-2026-00003",
    "CRM-OPP-2026-00004",
    "CRM-OPP-2026-00005",
]


def main():

    client = ERPNextClient()

    print("=" * 70)
    print("CHECK OPPORTUNITIES AND QUOTATIONS")
    print("=" * 70)

    for opportunity_name in OPPORTUNITIES:

        print(f"\n--- {opportunity_name} ---")

        try:
            bundle = client.get_opportunity_bundle(
                opportunity_name
            )

            opportunity = bundle["opportunity"]
            quotations = bundle["quotations"]

            print(
                "Opportunity:",
                opportunity.get("name")
            )

            print(
                "Opportunity From:",
                opportunity.get("opportunity_from")
            )

            print(
                "Party:",
                opportunity.get("party_name")
            )

            print(
                "Transaction Date:",
                opportunity.get("transaction_date")
            )

            print(
                "Amount:",
                opportunity.get("opportunity_amount")
            )

            print(
                "Quotation count:",
                len(quotations)
            )

            for q in quotations:
                print(
                    "  -",
                    q.get("name"),
                    "| date:",
                    q.get("transaction_date"),
                    "| discount:",
                    q.get(
                        "additional_discount_percentage"
                    ),
                )

        except Exception as e:

            print(
                "ERROR:",
                repr(e)
            )


if __name__ == "__main__":
    main()