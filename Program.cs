using System.Security.Claims;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.OpenApi;
using Scalar.AspNetCore;

var builder = WebApplication.CreateBuilder(args);

var keycloak = builder.Configuration.GetRequiredSection("Keycloak");
var authority = keycloak["Authority"]?.TrimEnd('/');
var audience = keycloak["Audience"];
var clientId = keycloak["ClientId"];
var requireHttpsMetadata = !builder.Environment.IsDevelopment()
    || keycloak.GetValue("RequireHttpsMetadata", true);

if (!Uri.TryCreate(authority, UriKind.Absolute, out var issuer)
    || (issuer.Scheme != Uri.UriSchemeHttps && issuer.Scheme != Uri.UriSchemeHttp)
    || !string.IsNullOrEmpty(issuer.Query)
    || !string.IsNullOrEmpty(issuer.Fragment)
    || !string.IsNullOrEmpty(issuer.UserInfo))
{
    throw new InvalidOperationException(
        "Set Keycloak:Authority to the realm URL, for example https://keycloak.example.com/realms/fileshub.");
}

if (issuer.Scheme == Uri.UriSchemeHttp && (requireHttpsMetadata || !issuer.IsLoopback))
{
    throw new InvalidOperationException(
        "Keycloak:Authority must use HTTPS. HTTP is allowed only for localhost in Development with Keycloak:RequireHttpsMetadata=false.");
}

if (string.IsNullOrWhiteSpace(audience) || string.IsNullOrWhiteSpace(clientId))
{
    throw new InvalidOperationException("Set Keycloak:Audience and Keycloak:ClientId.");
}

const string securityScheme = "Keycloak";

builder.Services
    .AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.Authority = authority;
        options.Audience = audience;
        options.RequireHttpsMetadata = requireHttpsMetadata;
        options.MapInboundClaims = false;
        options.TokenValidationParameters.NameClaimType = "preferred_username";
        options.TokenValidationParameters.ValidateIssuer = true;
        options.TokenValidationParameters.ValidateAudience = true;
        options.TokenValidationParameters.ValidateLifetime = true;
        options.TokenValidationParameters.ValidateIssuerSigningKey = true;
    });

builder.Services.AddAuthorization();

builder.Services.AddOpenApi(options =>
{
    options.AddDocumentTransformer((document, context, cancellationToken) =>
    {
        document.Info.Title = "Keycloak Test API";
        document.Info.Version = "v1";
        document.Components ??= new OpenApiComponents();
        document.Components.SecuritySchemes = new Dictionary<string, IOpenApiSecurityScheme>
        {
            [securityScheme] = new OpenApiSecurityScheme
            {
                Type = SecuritySchemeType.OAuth2,
                Description = "Sign in to Keycloak using authorization code with PKCE.",
                Flows = new OpenApiOAuthFlows
                {
                    AuthorizationCode = new OpenApiOAuthFlow
                    {
                        AuthorizationUrl = new Uri($"{authority}/protocol/openid-connect/auth"),
                        TokenUrl = new Uri($"{authority}/protocol/openid-connect/token"),
                        Scopes = new Dictionary<string, string>
                        {
                            ["openid"] = "OpenID Connect",
                            ["profile"] = "User profile",
                            ["email"] = "Email address"
                        }
                    }
                }
            }
        };

        // Only the two protected API endpoints are included in this document.
        foreach (var operation in document.Paths.Values.SelectMany(path => path.Operations!.Values))
        {
            operation.Security =
            [
                new OpenApiSecurityRequirement
                {
                    [new OpenApiSecuritySchemeReference(securityScheme, document)] = []
                }
            ];
        }

        return Task.CompletedTask;
    });
});

var app = builder.Build();

app.UseHttpsRedirection();
app.UseAuthentication();
app.UseAuthorization();

// Keep the documentation and login UI available in every environment.
app.MapOpenApi().AllowAnonymous();
app.MapScalarApiReference(options => options
    .WithTitle("Keycloak Test API")
    .DisableAgent()
    .DisableTelemetry()
    .DisableDefaultFonts()
    .AddPreferredSecuritySchemes(securityScheme)
    .AddAuthorizationCodeFlow(securityScheme, flow =>
    {
        flow.ClientId = clientId;
        flow.Pkce = Pkce.Sha256;
        flow.SelectedScopes = ["openid", "profile", "email"];
    }))
    .AllowAnonymous();

app.MapGet("/", () => Results.LocalRedirect("~/scalar/v1"))
    .AllowAnonymous()
    .ExcludeFromDescription();

var api = app.MapGroup("/api")
    .RequireAuthorization();

api.MapGet("/me", (ClaimsPrincipal user) => TypedResults.Ok(new UserDetails(
    user.FindFirstValue("sub"),
    user.FindFirstValue("preferred_username"),
    user.FindFirstValue("name"),
    user.FindFirstValue("email"),
    user.FindAll("groups")
        .Select(claim => claim.Value)
        .Distinct(StringComparer.Ordinal)
        .Order(StringComparer.Ordinal)
        .ToArray())))
    .Produces(StatusCodes.Status401Unauthorized)
    .WithSummary("Get the authenticated user's details and Keycloak groups.");

api.MapGet("/data", () => TypedResults.Ok(new[]
{
    new DataItem(1, "First sample item"),
    new DataItem(2, "Second sample item")
}))
    .Produces(StatusCodes.Status401Unauthorized)
    .WithSummary("Get sample data after authenticating with Keycloak.");

app.Run();

record UserDetails(string? Id, string? Username, string? Name, string? Email, string[] Groups);
record DataItem(int Id, string Name);
