from app.erpnext_client import ERPNextClient


OPPORTUNITY = "CRM-OPP-2026-00002"


def main():

    client = ERPNextClient()

    probability = 0.324008524322569
    band = "Thấp"

    fields = {
        "custom_win_probability": probability,
        "custom_win_band": band,
    }

    print("=" * 70)
    print("WIN PROBABILITY - ERPNext WRITE TEST")
    print("=" * 70)

    print("\nWriting:")
    print(fields)

    try:
        result = client.update_doc(
            "Opportunity",
            OPPORTUNITY,
            fields,
        )

        print("\n=== WRITE SUCCESS ===")
        print(result)

    except Exception as e:

        print("\n=== WRITE FAILED ===")
        print(repr(e))
        raise

    verified = client.get_doc(
        "Opportunity",
        OPPORTUNITY,
    )

    print("\n=== VERIFY ===")

    print(
        "custom_win_probability:",
        verified.get(
            "custom_win_probability"
        ),
    )

    print(
        "custom_win_band:",
        verified.get(
            "custom_win_band"
        ),
    )


if __name__ == "__main__":
    main()