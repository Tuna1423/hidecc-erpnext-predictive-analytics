from app.erpnext_client import ERPNextClient


def main():

    client = ERPNextClient()

    field = client.get_custom_field_options(
        "Opportunity",
        "custom_win_band",
    )

    print("=" * 70)
    print("WIN BAND FIELD")
    print("=" * 70)

    print("Name:", field.get("name"))
    print("Doctype:", field.get("dt"))
    print("Fieldname:", field.get("fieldname"))
    print("Fieldtype:", field.get("fieldtype"))
    print("Options:")
    print(field.get("options"))


if __name__ == "__main__":
    main()