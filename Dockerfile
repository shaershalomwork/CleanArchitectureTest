FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY KeycloakTestApi.csproj ./
RUN dotnet restore KeycloakTestApi.csproj
COPY . ./
RUN dotnet publish KeycloakTestApi.csproj -c Release -o /app/publish --no-restore /p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
WORKDIR /app
COPY --from=build /app/publish ./
USER $APP_UID
EXPOSE 8081
ENTRYPOINT ["dotnet", "KeycloakTestApi.dll"]
