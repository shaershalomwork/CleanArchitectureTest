# Keycloak Test API

A small .NET 10 Minimal API with Keycloak JWT authentication and Scalar.

| Route | Purpose | Authentication |
| --- | --- | --- |
| `/` | Redirect to Scalar at `/scalar/v1` | Public |
| `/scalar/v1` | Interactive documentation and Keycloak login | Public |
| `/openapi/v1.json` | OpenAPI document | Public |
| `GET /api/me` | User details and groups from the access token | Bearer token |
| `GET /api/data` | Two sample items | Bearer token |

## Run

Install the .NET 10 SDK and configure a Keycloak client as described below. The supplied authority URLs are **examples**, not a provisioned Keycloak server.

```powershell
dotnet dev-certs https --trust
dotnet restore
dotnet run --launch-profile Development
```

Open [https://localhost:7001](https://localhost:7001). The root redirects to Scalar. IDEs that honor `launchBrowser` open Scalar automatically; `dotnet run` starts the server and you open the URL yourself.

In Scalar, select **Keycloak**, authorize, and sign in in the Keycloak popup. Leave the client secret empty. Scalar uses authorization code with SHA-256 PKCE and sends the resulting access token as `Authorization: Bearer <token>` for both API endpoints.

## Keycloak client setup

Use an existing realm (for example `fileshub`) and create a separate OpenID Connect client:

| Setting | Value |
| --- | --- |
| Client ID | `keycloak-test-scalar` |
| Client authentication | OFF (public client) |
| Standard flow | ON |
| Implicit flow / Direct access grants / Service accounts | OFF |
| PKCE code challenge method | `S256` |
| Valid redirect URIs, local | `https://localhost:7001/scalar/v1` |
| Web origins, local | `https://localhost:7001` |

Scalar uses its current page URL as the callback, so open it at `/scalar/v1`. Register each deployed application's exact callback and origin as well, such as `https://api-test.example.com/scalar/v1` and `https://api-test.example.com`. Include any deployment path prefix. Use each environment's own realm/client where appropriate.

Attach the standard `profile` and `email` client scopes. Scalar requests `openid profile email`.

In **Clients > keycloak-test-scalar > Client scopes > keycloak-test-scalar-dedicated > Mappers**, add these two protocol mappers:

| Mapper type | Configuration |
| --- | --- |
| Audience | Name: `api-audience`; Included Custom Audience: `keycloak-test-api`; Add to access token: ON; Add to ID token: OFF |
| Group Membership | Name: `groups`; Token Claim Name: `groups`; Full group path: ON; Add to access token: ON |

Create a test user, give that user credentials, and join one or more realm groups. Use **Client scopes > Evaluate** to verify the access token contains `aud: "keycloak-test-api"` (or an array containing it) and `groups: ["/example-group"]`. Sign in again after mapper or group changes.

No client secret is required. The API validates access tokens using the realm's discovery document and signing keys. The API audience is distinct from Scalar's client ID, so the Scalar ID token is not a substitute for the API access token.

## Environments

ASP.NET Core loads `appsettings.json`, then `appsettings.{Environment}.json`, followed by environment-variable and command-line overrides.

| Environment | Supplied authority example | HTTP metadata |
| --- | --- | --- |
| Development | `http://localhost:8080/realms/fileshub` | Allowed for loopback hosts only |
| Test | `https://keycloak-test.example.com/realms/fileshub` | Disabled |
| Production | `https://keycloak.example.com/realms/fileshub` | Disabled |

Edit the relevant settings file or override its values:

```powershell
$env:Keycloak__Authority = "https://your-keycloak.example.com/realms/fileshub"
$env:Keycloak__Audience = "keycloak-test-api"
$env:Keycloak__ClientId = "keycloak-test-scalar"
dotnet run --launch-profile Test
```

For the other profiles, use `dotnet run --launch-profile Development` or `dotnet run --launch-profile Production`. Run one profile at a time because they share port 7001.

For deployment, set `ASPNETCORE_ENVIRONMENT` to `Test` or `Production`, supply the `Keycloak__*` settings, and configure the host's HTTPS binding/certificate. Launch profiles are local tooling settings and are not deployment configuration. If `DOTNET_ENVIRONMENT` is also set, keep it consistent with `ASPNETCORE_ENVIRONMENT`.

Required keys are `Keycloak:Authority`, `Keycloak:Audience`, and `Keycloak:ClientId`. Invalid or missing values stop startup. `Keycloak:RequireHttpsMetadata` defaults to true; Test and Production always enforce HTTPS even if it is set to false. Internal Keycloak certificates must be trusted by the application host and browser.

Scalar and OpenAPI are available in **every environment**. HTTPS redirection applies to application routes.

## Responses and checks

`GET /api/me` returns the validated access token's identity:

```json
{
  "id": "keycloak-user-id",
  "username": "alice",
  "name": "Alice Example",
  "email": "alice@example.com",
  "groups": ["/engineering", "/engineering/platform"]
}
```

Missing profile fields are `null`. Groups are distinct, sorted full paths; missing group claims return `[]`. Membership reflects token issuance time. Realm roles are separate from groups.

`GET /api/data` returns:

```json
[
  { "id": 1, "name": "First sample item" },
  { "id": 2, "name": "Second sample item" }
]
```

After starting the API:

```powershell
curl.exe -i https://localhost:7001/api/me
curl.exe -i https://localhost:7001/api/data
curl.exe -i -H "Authorization: Bearer invalid-token" https://localhost:7001/api/me
```

Unauthenticated and invalid-token calls must return `401`. After signing in through Scalar, both endpoints must return `200`. Check a user with multiple groups and one without groups. Tokens with an incorrect audience, issuer, or signature must fail; expired tokens fail after the JWT validator's default five-minute clock tolerance.

Repeat root, Scalar, OpenAPI, and unauthenticated checks using each launch profile.

| Problem | Check |
| --- | --- |
| Invalid redirect URI | Register the exact Scalar URL, including scheme, port, and path |
| Token request blocked by CORS | Set the Keycloak client's Web origins to the exact application origin |
| Login succeeds but API returns 401 | Inspect the access token's issuer, audience, expiry, and signature; use an access token, not an ID token |
| Empty groups | Enable the Group Membership mapper for access tokens, assign group membership, then sign in again |
| Discovery/TLS error | Verify the realm URL and host trust store; do not disable certificate validation |
| Missing name/email | Enable the profile/email scopes and populate those user attributes |

## Reference

The implementation follows the standard OIDC, trusted-token identity, and environment configuration approach in `C:\AAppPoolWeb\file-hub\docs\keycloak-integration-guide.md` and `apps/control-console/src/lib/auth.ts`. That application uses a confidential NextAuth client and realm roles. This API uses the selected public Scalar client with PKCE and reads groups from access tokens.

- [Scalar ASP.NET Core integration](https://scalar.com/products/api-references/integrations/aspnetcore/integration)
- [ASP.NET Core JWT bearer authentication](https://learn.microsoft.com/en-us/aspnet/core/security/authentication/configure-jwt-bearer-authentication?view=aspnetcore-10.0)
- [Keycloak client configuration](https://www.keycloak.org/securing-apps/javascript-adapter)
