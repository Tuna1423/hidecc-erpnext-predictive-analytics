from pprint import pprint

from app.erpnext_client import ERPNextClient
from app.feature_builder import DELAY_FEATURES, build_delay_features


def main():
    client = ERPNextClient()

    print("Fetching ERPNext data...")
    bundle = client.get_project_bundle("PROJ-0001")

    print("Building Delay Risk features...")
    features = build_delay_features(bundle)

    print("\n=== FEATURE ROWS ===")
    print(f"Number of rows: {len(features)}")

    print("\n=== MODEL FEATURES ===")
    print(features[DELAY_FEATURES].to_string(index=False))

    print("\n=== CHECK ===")

    missing = features[DELAY_FEATURES].isna().sum()

    print("\nMissing values:")
    print(missing[missing > 0])

    print("\nDtypes:")
    print(features[DELAY_FEATURES].dtypes)

    print("\nFeature columns:")
    pprint(list(features[DELAY_FEATURES].columns))


if __name__ == "__main__":
    main()