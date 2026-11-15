# Direct UPI payment flow

Payments are sent from the farmer's UPI app directly to the UPI ID configured by the owner. KISAN-X does not collect card or bank credentials, hold money, or use a payment gateway. A farmer submits a UPI reference (UTR) and an optional receipt image. The owner checks the credit in their own banking/UPI app and approves or rejects the claim manually.

## Local configuration

Public claims and payment status lookup are disabled unless `KISANX_ENABLE_PUBLIC_PAYMENT_CLAIMS=true`. Keep this false for the public demo: it has no farmer sign-in, per-farmer privacy, persistent private receipt storage, or plan feature gating. Do not collect real payment proofs until those controls are implemented and reviewed.


1. Add `KISANX_OWNER_PIN` to the project root `.env`; use a private value of at least six characters. There is no default owner PIN.
2. Start the FastAPI app. The SQLAlchemy database initializes the owner settings, tiers, claims, and subscriptions on startup when `AUTO_CREATE_TABLES=true`.
3. Open **Plans & upgrade**, then open **Owner payment settings**. Unlock with the PIN and configure the owner's UPI ID, payee name, and QR image.
4. The farmer selects a paid tier, pays in their UPI app, then submits their UTR and optional screenshot. The UI does not claim the payment has settled.
5. The owner reviews the UTR/amount in their own account before using Approve. Approval activates the subscription for the tier duration.

The backend dependency `python-multipart` supports form uploads. QR images are stored at `backend/data/payment_uploads/qr/` and served only through `/api/v1/pay/qr`. Payment proofs are stored at `backend/data/payment_uploads/proofs/`, which is not mounted as a static directory; proof retrieval requires `X-Owner-Pin`.

## API routes

| Route | Access | Purpose |
|---|---|---|
| `GET /api/v1/pay/public-config` | Public | Active plans and owner UPI/QR configuration |
| `GET /api/v1/pay/qr` | Public | Owner's QR image |
| `POST /api/v1/pay/submit-claim` | Public | Multipart UTR claim and optional screenshot |
| `POST /api/v1/pay/status` | Public when enabled | One matching claim status using phone + UPI reference in the JSON body |
| `GET /api/v1/owner/dashboard` | `X-Owner-Pin` | Claims, plan settings, and totals |
| `POST /api/v1/owner/verify-claim` | `X-Owner-Pin` | Approve/reject a pending claim |
| `GET /api/v1/owner/claims/{claim_id}/proof` | `X-Owner-Pin` | Private proof image |
| `POST /api/v1/owner/update-settings` | `X-Owner-Pin` | UPI details, QR, and tier edits |

## Boundaries to keep visible

- Farmer mobile number is the prototype identifier; the status endpoint is not account authentication. Add verified sign-in before a real paid rollout.
- There is no automatic UPI settlement verification or refund workflow. The owner must reconcile each claim manually.
- Subscription records are not connected to feature-level authorization in this prototype. The plans UI explicitly tells farmers that paid feature gating is not yet active.
- Payment proofs may include personal data. Restrict database and filesystem access and define a retention/deletion schedule before launch.
- Recheck consumer, tax, privacy, and payment obligations with qualified local counsel before collecting real payments.

For a migrated database, `alembic upgrade head` applies `0002_direct_upi_payments`; startup also seeds the default owner row and tier descriptions.
