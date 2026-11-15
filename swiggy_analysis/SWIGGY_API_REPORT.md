# Swiggy Android — API & Payload Inventory

**Target:** `in.swiggy.android` — Swiggy **v4.120.1** (versionCode 1866)  
**Method:** static reverse engineering of the shipped APK (jadx 1.5.1 + pyaxmlparser). No live traffic was captured or replayed.

| Property | Value |
|---|---|
| Package | `in.swiggy.android` |
| Version | 4.120.1 (1866) |
| minSdk / targetSdk | 32 / 36 |
| APK size | 88.5 MB |
| DEX files | 8 (`classes.dex` … `classes8.dex`), ~76 MB |
| Native libs | none (`lib/` empty — pure Java/Kotlin) |
| Classes decompiled | 27,156 |
| APK MD5 | `97887825a7ca3fef1fdd3599b8b84a83` |
| APK SHA-256 | `341e7d65704cabae1683de44e65de9483f30985db5b0f783de00b82e897e503f` |

## Headline numbers

- **279 unique endpoints** (318 method+path+interface declarations)
- **98 Retrofit interfaces**
- **116 GET / 185 POST / 12 PUT / 4 DELETE / 1 PATCH**
- **1117 payload model classes**, **4853 JSON fields**
- **15 feature groups**

## 1. Hosts seen in the APK

| Host | refs | Role |
|---|---|---|
| `media-assets.swiggy.com` | 59 | Static media / image CDN (largest count) |
| `instamart-media-assets.swiggy.com` | 28 | Instamart asset CDN |
| `www.swiggy.com` | 17 | Main web host — `/mapi/help/resources` path observed here |
| `payments.swiggy.com` | 14 | Payment webview + `/connect` |
| `webviews.swiggy.com` | 12 | Generic webview container |
| `stores.swiggy.com` | 4 | Restaurant/store webview + `/connect` |
| `toing-media-assets.swiggy.com` | 4 | Toing asset CDN |
| `dineout-media-assets.swiggy.com` | 3 | Dineout asset CDN |
| `disc.swiggy.com` | 3 | `/api/v2/launch`, `/connect` (device/attribution bootstrap) |
| `insanelygood.swiggy.com` | 2 | InsanelyGood |
| `instamax.swiggy.com` | 2 | Instamax |
| `maps.swiggy.com` | 2 | Maps webview + `/connect` |
| `profile.swiggy.com` | 2 | Profile webview |

| `analytics.swiggy.com` | 1 | Analytics ingestion |
| `app.swiggy.com` | 1 | App webview |
| `chkout.swiggy.com` | 1 | — |
| `dash.swiggy.com` | 1 | Dash — order history / refunds |
| `dinersone-proxy.swiggy.com` | 1 | Dinersone proxy (Dineout) |
| `fna.swiggy.com` | 1 | F&A |
| `fulfillment-middleware.swiggy.com` | 1 | Fulfillment middleware |
| `payments-staging.swiggy.com` | 1 | Payment staging env |
| `pos.swiggy.com` | 1 | POS integration |
| `promos.swiggy.com` | 1 | — |
| `spns.swiggy.com` | 1 | Push notification service |
| `tns.swiggy.com` | 1 | — |

**Third-party / non-Swiggy hosts of note** (payment + analytics + ads):

| Host | refs |
|---|---|
| `www.w3.org` | 35 |
| `googleads.g.doubleclick.net` | 8 |
| `www.slf4j.org` | 8 |
| `api.mixpanel.com` | 6 |
| `developer.android.com` | 6 |
| `developers.facebook.com` | 5 |
| `www.google.com` | 5 |
| `goo.gl` | 4 |
| `firebase.google.com` | 4 |
| `github.com` | 4 |
| `goo.gle` | 4 |

| `schemas.android.com` | 3 |
| `xml.org` | 3 |
| `assets.juspay.in` | 3 |
| `b67f7794189c.edge.sdk.awswaf.com` | 3 |
| `issuetracker.google.com` | 3 |
| `secure.payu.in` | 3 |
| `test.payu.in` | 3 |
| `dashif.org` | 2 |
| `xmlpull.org` | 2 |
| `amazonpay.amazon.in` | 2 |
| `app-measurement.com` | 2 |
| `de-docs.s3.amazonaws.com` | 2 |
| `exoplayer.dev` | 2 |
| `firebase-settings.crashlytics.com` | 2 |
| `firebaseremoteconfig.googleapis.com` | 2 |
| `firebaseremoteconfigrealtime.googleapis.com` | 2 |
| `info.payu.in` | 2 |
| `ktor.io` | 2 |

> **Important:** the Retrofit **base URL is injected at runtime via DI**, not hardcoded as a single literal. Paths below are relative to that injected per-service base. `www.swiggy.com` is the primary candidate for the food API surface.

## 2. Auth, session and custom headers

Header names observed in the network layer (interceptors, header maps, Lynx bridge):

| Header | Where |
|---|---|
| `x-swiggy-auth` | Set as request header AND read back from response — session/identity token (`network/interceptors/b.java`) |
| `sid` | Session id — serialized in device-details payload (`services/devicedetails/c.java`), used in analytics events |
| `swuid` | Swiggy user id — analytics + webview cookie/header |
| `userId` | User id in request payloads and headers |
| `device_id` / `X-DEVICE-ID` | Device identifier |
| `app-session-id` / `session-id` | App session |
| `x-message-id` | Chat message idempotency key (`IChatNotificationApi`) |
| `Authorization` | Bearer token on selected APIs (`ISpnsApi`, Bureau device events) |
| `X-Api-Key` | API key header |
| `X-Discovery-Context` | Discovery context |
| `encoded-location-context` | Base64/encoded lat-lng context |
| `encoded-loyalty-context` | Encoded loyalty (Swiggy One) context |
| `encoded-menu-body` | Encoded menu request body |
| `fresh-gps-location`, `last-known-location`, `inaccuracy-in-metres`, `gps-fetch-count`, `gps-fetch-success` | GPS metadata headers |
| `x-device-width`, `x-device-height`, `x-device-memory`, `x-device-network`, `x-device-frame` | Device fingerprint headers |
| `cart-half-card`, `half-card-source` | Cart UI context |
| `x-org-id: marketplace` | Static org header on Instamart relay APIs |
| `Content-Encoding: gzip` | On `v1/deviceService/config` |
| `TIMEOUT_MS`, `MAX_RETRY_COUNT` | Per-call tuning headers |
| `tenant` | Juspay auth-token lookup |
| `edges` / `X-Amzn-Waf-Rate-Limit` | AWS WAF token handling (`network/waf/`) |

**Device fingerprint payload** (`in/swiggy/android/services/devicedetails/c.java`) serializes: `appVersionCode`, `deviceId`, `deviceManufacturer`, `deviceModel`, `deviceRooted`, `latitude`, `longitude`, `networkCarrier`, `networkType`, `osVersion`, `platform`, `playServiceVersion`, `sequenceNumber`, `sid`, `userId` → sent to the data platform.

## 3. Full endpoint inventory by feature

### Analytics / Telemetry / Devices  (14)

| Method | Path | Interface | Fn |
|---|---|---|---|
| `GET` | `/api/v1/entity/{entityType}/{entityId}` | `a` | `a` |
| `GET` | `/api/v1/entity/{entityType}/{entityId}/json` | `a` | `b` |
| `GET` | `/client/metric/event/gtm` | `IMessageApi` | `sendGTMEvent` |
| `GET` | `v1/deviceService/config` | `a` | `a` |
| `POST` | `/api/v1/app/screenshots/upload-urls` | `o` | `a` |
| `POST` | `/message` | `IMessageApi` | `sendMessage` |
| `POST` | `/message-set` | `IMessageApi` | `sendBulkMessage` |
| `POST` | `analytics/transactional/device/add/` | `ISpnsApi` | `registerDeviceSPNS` |
| `POST` | `api/fraudnabuse/v1/fact/device-session/fingerprint` | `IFnaApi` | `sendDeviceIdSignals` |
| `POST` | `api/v1/events/event-status` | `IMatchHoursAPI` | `fetchMultiEventStatus` |
| `POST` | `topics/aws.msk.bureau.androidDeviceEvents` | `a` | `a` |
| `POST` | `v1/deviceService/deviceData/android` | `f1` | `a` |
| `PUT` | `addresses/event/v1` | `IAddressMapsJsonApi` | `partialAddressUpdate` |
| `PUT` | `addresses/event/v1` | `IAddressMapsProtoApi` | `partialAddressUpdate` |

### Auth / Login / OTP / Signup  (23)

| Method | Path | Interface | Fn |
|---|---|---|---|
| `GET` | `api/v1/landing-page/POST_SIGNUP` | `IGiftRevealPostSignupApi` | `giftPostSignUp` |
| `GET` | `api/v2/app/call_otp` | `h` | `c` |
| `GET` | `api/v2/app/login_check` | `h` | `f` |
| `GET` | `api/v2/app/sms_otp` | `h` | `g` |
| `GET` | `api/v3/app/sms_otp` | `IRequestOtpApi` | `requestSmsOtp` |
| `GET` | `api/v3/app/sms_otp` | `h` | `h` |
| `POST` | `/api/v3/app/shell_login_check` | `IShellLoginApi` | `shellLoginCheck` |
| `POST` | `/v1/accounts/signInWithTID` | `IOzoneApi` | `signInWithTid` |
| `POST` | `/v1/token/refresh` | `IOzoneApi` | `refreshAccessToken` |
| `POST` | `api/v1/app/login/call_verification_status` | `IOtpVerificationApi` | `getCallVerificationStatus` |
| `POST` | `api/v2/app/login/verify` | `IOtpVerifyApi` | `verifyOtp` |
| `POST` | `api/v2/app/request_call_verification` | `IOtpVerificationApi` | `initiateCallVerification` |
| `POST` | `api/v2/app/signup` | `h` | `b` |
| `POST` | `api/v2/app/whatsapp_otp` | `IOtpVerificationApi` | `requestWhatsappOtp` |
| `POST` | `api/v3/app/login/call_verification_status` | `IOtpVerificationApi` | `getCallVerificationStatusV3` |
| `POST` | `api/v3/app/login/call_verification_status` | `IRequestOtpApi` | `fetchCallVerificationStatus` |
| `POST` | `api/v3/app/login/verify` | `IOtpVerifyApi` | `verifyOtpV3` |
| `POST` | `api/v3/app/request_call_verification` | `IOtpVerificationApi` | `initiateCallVerificationV3` |
| `POST` | `api/v3/app/request_call_verification` | `IRequestOtpApi` | `requestCallVerification` |
| `POST` | `api/v3/app/signup` | `ISignUpApi` | `signUpUser` |
| `POST` | `api/v3/app/whatsapp_otp` | `IOtpVerificationApi` | `requestWhatsappOtpV3` |
| `POST` | `api/v3/app/whatsapp_otp` | `IRequestOtpApi` | `requestWhatsappOtp` |
| `PUT` | `api/v1/user/mobile/otpverify` | `h` | `e` |

### Cart  (6)

| Method | Path | Interface | Fn |
|---|---|---|---|
| `DELETE` | `api/v2/cart/client/flush` | `a` | `c` |
| `GET` | `/api/v2/view?cartType=INSTAMART` | `IInstamartApi` | `getInstamartCart` |
| `POST` | `/api/v2/view/clear-cart?cartType=INSTAMART` | `IInstamartApi` | `clearInstamartCart` |
| `POST` | `api/v2/cart/client/check_totals` | `ICheckoutClientCartApi` | `updateGuestCartMro` |
| `POST` | `api/v2/cart/client/update` | `ICheckoutClientCartApi` | `updateCart` |
| `POST` | `api/v2/view/INSTAMART?pageType=INSTAMART_CART` | `IInstamartApi` | `getInstamartCartWithLayoutDetails` |

### Content / Pages  (7)

| Method | Path | Interface | Fn |
|---|---|---|---|
| `GET` | `` | `a` | `a` |
| `GET` | `/api/v1/gallerypage` | `a` | `a` |
| `GET` | `/api/v1/gallerypage/json` | `a` | `b` |
| `GET` | `/api/v1/overlays` | `a` | `b` |
| `GET` | `/api/v2/fetchNotification` | `a` | `a` |
| `GET` | `api/v1/cricket/match-status` | `IMatchHoursAPI` | `fetchMatchState` |
| `POST` | `/api/v1/overlays/poll` | `a` | `a` |

### Dineout  (15)

| Method | Path | Interface | Fn |
|---|---|---|---|
| `GET` | `/api/v1/dineout_collection` | `b` | `e` |
| `GET` | `/api/v1/json/dineout_collection` | `b` | `g` |
| `GET` | `/api/v3/BUSINESS_LINE_DINEOUT/offer` | `IOfferV3DineoutAPI` | `getV3DineoutCouponList` |
| `GET` | `/api/v3/BUSINESS_LINE_DINEOUT/offer/json` | `IOfferV3DineoutAPI` | `getV3DineoutCouponListJSON` |
| `GET` | `api/dinersone/{pageID}` | `b` | `f` |
| `GET` | `api/dinersone/{pageID}/json` | `b` | `k` |
| `POST` | `/api/v1/json/{pageID}` | `b` | `c` |
| `POST` | `/api/v1/user/upcoming-bookings` | `b` | `j` |
| `POST` | `/api/v1/user/upcoming-bookings/json` | `b` | `a` |
| `POST` | `/api/v1/user/usersignal` | `IDineoutFavouriteApi` | `callFavApi` |
| `POST` | `/api/v1/{pageID}` | `b` | `h` |
| `POST` | `/api/v1/{pageID}/json` | `b` | `d` |
| `POST` | `/api/v2/view/DINEOUT` | `c` | `a` |
| `POST` | `/api/v2/view/getBill/json` | `d` | `c` |
| `POST` | `/api/v2/view/getBill/proto` | `d` | `a` |

### Instamart  (14)

| Method | Path | Interface | Fn |
|---|---|---|---|
| `GET` | `/address/recommend` | `d` | `a` |
| `GET` | `/api/v1/instamart/complimentary_item` | `b` | `h` |
| `GET` | `/api/v1/instamart/seo-product` | `b` | `k` |
| `GET` | `/api/v1/instamart/{pageID}` | `b` | `g` |
| `GET` | `/api/v1/instamart/{pageId}` | `b` | `b` |
| `GET` | `/api/v2/instamart/{pageID}` | `b` | `c` |
| `POST` | `/api/v1/instamart/pass/activate` | `IPassApi` | `activatePass` |
| `POST` | `/api/v1/instamart/product` | `b` | `l` |
| `POST` | `/api/v1/instamart/user-preferences/update` | `IUserPreferenceApi` | `updateUserPreferences` |
| `POST` | `/api/v1/instamart/{pageID}` | `b` | `d` |
| `POST` | `/api/v1/instamart/{pageId}` | `b` | `m` |
| `POST` | `/api/v1/pre-select` | `IPreSelectApi` | `preSelect` |
| `POST` | `api/v1/instamart/print_preview` | `IPrintApi` | `requestPreviewDocData` |
| `POST` | `api/v2/view/INSTAMART?pageType=INSTAMART_HOME` | `IInstamartApi` | `updateCart` |

### Maps / Location / Address  (23)

| Method | Path | Interface | Fn |
|---|---|---|---|
| `GET` | `/address/homepage` | `IRecommendsApi` | `getRecommendsListFromHomePageApi` |
| `GET` | `/address/recommend` | `IKmmRecommendsApi` | `getRecommedsListFromLatlng` |
| `GET` | `/address/recommend` | `IRecommendsApi` | `getRecommedsListFromLatlng` |
| `GET` | `addresses/defaulting/v1/all?clientId=android-consumer-app` | `IAddressMapsJsonApi` | `getAllDefaultingAddresses` |
| `GET` | `addresses/defaulting/v1/all?clientId=android-consumer-app` | `IAddressMapsProtoApi` | `getAllDefaultingAddresses` |
| `GET` | `addresses/v1` | `IAddressMapsJsonApi` | `getAddressById` |
| `GET` | `addresses/v1` | `IAddressMapsProtoApi` | `getAddressById` |
| `GET` | `addresses/v1/all?client_id=android-consumer-app` | `IAddressMapsJsonApi` | `getAllAddresses` |
| `GET` | `addresses/v1/all?client_id=android-consumer-app` | `IAddressMapsProtoApi` | `getAllAddresses` |
| `GET` | `api/v1/location_based_features` | `ILocationBasedFeatureAPI` | `getLocationBasedFeatures` |
| `GET` | `getlink/v1` | `IAddressDeepLinkApi` | `getAddressDeepLink` |
| `GET` | `signed-url/upload/address-images` | `a` | `a` |
| `GET` | `signed-url/upload/voice-directions` | `a` | `d` |
| `POST` | `/api/v1/ai/analyze` | `a` | `a` |
| `POST` | `/api/v1/json/update_frequency_counter` | `c` | `a` |
| `POST` | `/api/v1/update_frequency_counter` | `c` | `b` |
| `POST` | `/directions` | `IDirectionsSwiggyApi` | `getDirections` |
| `POST` | `addresses/v1` | `IAddressMapsJsonApi` | `addAddress` |
| `POST` | `addresses/v1` | `IAddressMapsProtoApi` | `addAddress` |
| `POST` | `api/v2/pop/address/add` | `IAddressMapsProtoApi` | `addPopAddress` |
| `POST` | `signed-url/download` | `a` | `b` |
| `PUT` | `addresses/v1` | `IAddressMapsJsonApi` | `updateAddress` |
| `PUT` | `addresses/v1` | `IAddressMapsProtoApi` | `updateAddress` |

### Menu & Restaurant  (67)

| Method | Path | Interface | Fn |
|---|---|---|---|
| `GET` | `/api/dinersone/useronboarding` | `b` | `b` |
| `GET` | `/api/dinersone/useronboarding/json` | `b` | `f` |
| `GET` | `/api/v1/digital-menu/config` | `b` | `h` |
| `GET` | `/api/v1/digital-menu/config/json` | `b` | `e` |
| `GET` | `/api/v1/dinersone-restaurant` | `b` | `b` |
| `GET` | `/api/v1/dinersone-restaurant/json` | `b` | `a` |
| `GET` | `/api/v1/entity/ENTITY_DINEOUT_MENU/{restaurantId}` | `b` | `l` |
| `GET` | `/api/v1/entity/ENTITY_DINEOUT_MENU/{restaurantId}/json` | `b` | `c` |
| `GET` | `/api/v1/item_collection/json/{collection_id}` | `ILandingAPI` | `getItemCollectionV1Json` |
| `GET` | `/api/v1/item_collection/json/{collection_id}` | `IMenuItemCollection` | `getItemCollectionJson` |
| `GET` | `/api/v1/item_collection/{collection_id}` | `ILandingAPI` | `getItemCollectionV1` |
| `GET` | `/api/v1/item_collection/{collection_id}` | `IMenuItemCollection` | `getItemCollection` |
| `GET` | `/api/v1/restaurant/brand/{brandId}` | `IBrandApi` | `getRestaurantID` |
| `GET` | `/api/v1/restaurant/{restaurantId}/deal-detail` | `a` | `b` |
| `GET` | `/api/v1/restaurant/{restaurantId}/deal-detail/json` | `a` | `a` |
| `GET` | `/api/v2/staticmenu/{restaurantId}` | `IMenuListingAPI` | `getStaticMenuListing` |
| `GET` | `/api/v4/restaurant/otheroutlets/{restaurantId}` | `IOldOutletSelectorApi` | `getOldOutletSelectorList` |
| `POST` | `/api/v1/cross-pollination/update-engagement` | `a` | `a` |
| `POST` | `/api/v1/digital-menu/qr-scan` | `b` | `n` |
| `POST` | `/api/v1/digital-menu/qr-scan/json` | `b` | `p` |
| `POST` | `/api/v1/digital-menu/user-session-configs/claim` | `b` | `d` |
| `POST` | `/api/v1/digital-menu/user-session-configs/claim/json` | `b` | `a` |
| `POST` | `/api/v1/dineout_item_collection/json/{pageID}` | `b` | `i` |
| `POST` | `/api/v1/dineout_item_collection/{pageID}` | `b` | `b` |
| `POST` | `/api/v1/dinersone-restaurant` | `d` | `d` |
| `POST` | `/api/v1/dinersone-restaurant/json` | `d` | `b` |
| `POST` | `/api/v1/json/layout-section/CROSS_SELL_DINEOUT` | `b` | `j` |
| `POST` | `/api/v1/json/layout-section/{sectionId}` | `IMenuListingAPI` | `getCrossSellJsonItems` |
| `POST` | `/api/v1/json/layout-section/{sectionId}` | `IOutletSelectorApi` | `getOutletSelectorsJsonList` |
| `POST` | `/api/v1/json/layout-section/{sectionId}` | `IRelevanceAPI` | `getRelevantJsonItems` |
| `POST` | `/api/v1/layout-section/CROSS_SELL_DINEOUT` | `b` | `g` |
| `POST` | `/api/v1/layout-section/{sectionId}` | `IMenuListingAPI` | `getCrossSellItems` |
| `POST` | `/api/v1/layout-section/{sectionId}` | `IOutletSelectorApi` | `getOutletSelectorsList` |
| `POST` | `/api/v1/layout-section/{sectionId}` | `IRelevanceAPI` | `getRelevantItems` |
| `POST` | `/api/v1/menu/search` | `IAipSearchAPI` | `getAipSearchResponse` |
| `POST` | `/api/v1/menu/search` | `ICollectionSearchAPI` | `getCollectionSearchResponse` |
| `POST` | `/api/v1/menu/search` | `IMenuListingAPI` | `getSearchListing` |
| `POST` | `/api/v1/menu/search/json` | `IAipSearchAPI` | `getAipSearchJsonResponse` |
| `POST` | `/api/v1/menu/search/json` | `ICollectionSearchAPI` | `getCollectionSearchJsonResponse` |
| `POST` | `/api/v1/menu/search/json` | `IMenuListingAPI` | `getSearchJsonListing` |
| `POST` | `/api/v1/quickActions/submit/json` | `b` | `k` |
| `POST` | `/api/v1/quickActions/submit/proto` | `b` | `q` |
| `POST` | `/api/v2/dynamicmenu/{restaurantId}` | `IMenuListingAPI` | `getDynamicMenuListing` |
| `POST` | `/api/v2/item_collection/json/{collection_id}` | `ILandingAPI` | `getItemCollectionV2Json` |
| `POST` | `/api/v2/item_collection/{collection_id}` | `ILandingAPI` | `getItemCollectionV2` |
| `POST` | `/api/v2/meal_collection/json/{collection_id}` | `ILandingAPI` | `getMealCollectionJson` |
| `POST` | `/api/v2/meal_collection/{collection_id}` | `ILandingAPI` | `getMealCollection` |
| `POST` | `/api/v2/menu/{restaurantId}` | `IMenuListingAPI` | `getMenuListing` |
| `POST` | `/api/v2/resolve/menu/{restaurantName}` | `IMenuListingAPI` | `getResolveMenuListing` |
| `POST` | `/api/v2/view/pin/json` | `b` | `r` |
| `POST` | `/api/v2/view/pin/proto` | `b` | `i` |
| `POST` | `/api/v2/view/verify-pin/json` | `b` | `m` |
| `POST` | `/api/v2/view/verify-pin/proto` | `b` | `s` |
| `POST` | `/api/v3/collection/restaurant/json/{collectionId}` | `ILandingAPI` | `getCollectionV3Json` |
| `POST` | `/api/v3/collection/restaurant/{collectionId}` | `ILandingAPI` | `getCollectionV3` |
| `POST` | `api/v1/json/layout-section/CROSS_SELL` | `ICrossSellAPI` | `getCrossSellCollectionJSON` |
| `POST` | `api/v1/json/layout-section/PRE_SEARCH` | `ISearchResultsJsonApi` | `getPreSearchLayoutSection` |
| `POST` | `api/v1/json/layout-section/{sectionId}` | `a` | `b` |
| `POST` | `api/v1/layout-section/CROSS_SELL` | `ICrossSellAPI` | `getCrossSellCollection` |
| `POST` | `api/v1/layout-section/PRE_SEARCH` | `ISearchResultsProtobufAPI` | `getPreSearchLayoutSection` |
| `POST` | `api/v1/layout-section/{sectionId}` | `a` | `a` |
| `POST` | `api/v1/user/dislike` | `IDislikeApi` | `markDislike` |
| `POST` | `api/v1/user/favorite` | `IFavouriteAPI` | `markFavourite` |
| `POST` | `api/v3/json/search/dish-add` | `ISearchMoreOptionsJsonApi` | `getMoreOptionsFromRestaurant` |
| `POST` | `api/v3/search/dish-add` | `ISearchMoreOptionsProtoApi` | `getMoreOptionsFromRestaurant` |
| `PUT` | `/api/v1/digital-menu/user-session-configs/consent` | `b` | `o` |
| `PUT` | `/api/v1/digital-menu/user-session-configs/consent/json` | `b` | `t` |

### Offers / Coupons / Referral  (9)

| Method | Path | Interface | Fn |
|---|---|---|---|
| `GET` | `/api/v2/offer` | `IOfferV2API` | `getV2CouponList` |
| `GET` | `/api/v2/offer/json` | `IOfferV2API` | `getV2CouponListJSON` |
| `GET` | `api/v1/referrer/check` | `IReferralApi` | `checkReferralEligibility` |
| `POST` | `/api/v1/offer` | `IOffersApi` | `getOfferDetail` |
| `POST` | `api/v1/referral/intrigue` | `IGiftIntrigueApi` | `giftIntrigueApi` |
| `POST` | `api/v1/referral/reveal` | `IGiftRevealApi` | `revealOffer` |
| `POST` | `api/v1/referral/validity` | `IReferralApi` | `renewExpiryCoupon` |
| `POST` | `api/v1/referrer/contact` | `IReferralApi` | `postPhoneNoRequestForContactSync` |
| `POST` | `api/v1/reward` | `IGiftRevealRewardApi` | `giftReward` |

### Order & Tracking  (35)

| Method | Path | Interface | Fn |
|---|---|---|---|
| `DELETE` | `/api/v1/shared_cart` | `a` | `f` |
| `GET` | `/api/v1/dash/oms/order/{id}/context/ORDER_JOB` | `c` | `getOrderByJobId` |
| `GET` | `/api/v1/digital-menu/customer/ordered-items` | `a` | `a` |
| `GET` | `/api/v1/order/history` | `b` | `a` |
| `GET` | `/api/v1/shared_cart` | `a` | `a` |
| `GET` | `/api/v1/timeline/orderjob/{orderJobID}` | `c` | `a` |
| `GET` | `/api/v1/timeline/{timelineUserType}/tracking/{trackingId}` | `c` | `d` |
| `GET` | `/api/v1/tracking/orderjob/{id}` | `c` | `f` |
| `GET` | `/api/v1/widgets` | `a` | `a` |
| `GET` | `/api/v1/widgets` | `b` | `a` |
| `GET` | `/api/v2/help/issues` | `IOrderHelpAPI` | `getHelpSupport` |
| `GET` | `/v3/order/receiver-update-eligible` | `a` | `a` |
| `GET` | `api/v1/account/orders` | `IOrderHistoryProtoAPI` | `getGiftingOrderHistory` |
| `GET` | `api/v1/dash/oms/order/history` | `c` | `a` |
| `GET` | `api/v1/json/account/orders` | `IOrderHistoryJsonAPI` | `getGiftingOrderHistory` |
| `GET` | `api/v2/help/issues/order` | `g` | `b` |
| `GET` | `v3/order/address-update-eligible` | `a` | `a` |
| `POST` | `/api/v1/checkout/order` | `c` | `b` |
| `POST` | `/api/v1/dash/oms/order-job/{orderjob}/status` | `c` | `c` |
| `POST` | `/api/v1/dash/rating` | `c` | `b` |
| `POST` | `/api/v1/dash/rating/dismiss` | `c` | `e` |
| `POST` | `/api/v1/instamart/relay-vendor-order` | `IRelayVendorApi` | `callRelayVendorApi` |
| `POST` | `/api/v1/instamart/relay-verification-order` | `IRelayVendorApi` | `callRelayVerificationOrderApi` |
| `POST` | `/api/v1/json/poll-widgets` | `b` | `b` |
| `POST` | `/api/v1/poll-widgets` | `a` | `b` |
| `POST` | `/api/v1/shared_cart/create` | `a` | `c` |
| `POST` | `/api/v1/shared_cart/join` | `a` | `e` |
| `POST` | `/api/v1/shared_cart/unlock` | `a` | `b` |
| `POST` | `/api/v1/shared_cart/update` | `a` | `d` |
| `POST` | `/api/v4/order/edit` | `IEditOrderApi` | `updateDeliveryInstructions` |
| `POST` | `/api/v4/order/edit` | `b` | `a` |
| `POST` | `/directions` | `a` | `a` |
| `POST` | `addresses/v1/nearby-eligible` | `c` | `a` |
| `POST` | `api/v1/ratings/order` | `IEdmApi` | `postEdmRating` |
| `PUT` | `v1/cancel-only/order/{orderId}` | `ICancelOnlyApi` | `cancelOnly` |

### Other  (18)

| Method | Path | Interface | Fn |
|---|---|---|---|
| `GET` | `` | `c` | `a` |
| `GET` | `` | `d` | `a` |
| `GET` | `/api/v1/entity/DINECASH_DEAL_DETAIL/{voucherId}` | `a` | `b` |
| `GET` | `/api/v1/entity/DINECASH_DEAL_DETAIL/{voucherId}/json` | `a` | `a` |
| `GET` | `/api/v1/entity/VOUCHER/{voucherId}` | `b` | `a` |
| `GET` | `/api/v1/entity/VOUCHER/{voucherId}/json` | `b` | `b` |
| `POST` | `/api/v1/instaprint/batch-generate-pre-signed-upload-url` | `IPrintApi` | `generatePreSignedURL` |
| `POST` | `/api/v1/instaprint/batch-validate-document` | `IPrintApi` | `validateDocument` |
| `POST` | `/api/v1/review/meta` | `IRatingApi` | `getReviewsMeta` |
| `POST` | `api/fraudnabuse/v1/entity` | `IFnaApi` | `sendTnsSignals` |
| `POST` | `api/v1/app/logout` | `h` | `a` |
| `POST` | `api/v1/config/preLaunch` | `IPreLaunchAPI` | `getPreLaunchData` |
| `POST` | `api/v1/config/settings` | `ISettingsApi` | `getSettingsResponse` |
| `POST` | `api/v1/config/settings` | `h` | `getSettingsResponse` |
| `POST` | `api/v1/launch-configs` | `ILaunchConfigAPI` | `getLaunchConfigData` |
| `POST` | `api/v1/review/dismiss` | `IRatingDismissApi` | `dismissRating` |
| `POST` | `api/v2/ratings/create` | `g` | `d` |
| `PUT` | `/api/v1/review` | `IRatingSubmitApi` | `postSubmitRating` |

### Payments & UPI  (23)

| Method | Path | Interface | Fn |
|---|---|---|---|
| `DELETE` | `/payment/presentation/v1/refunds/clearNotification` | `IRefundsAPI` | `removeRefundsNotification` |
| `DELETE` | `payment/presentation/api/v1/upi/delete` | `IPaymentApi` | `deleteSavedVpa` |
| `GET` | `/api/v1/dash/oms/order/{orderJobId}/context/ORDER_JOB` | `IDashPaymentApi` | `getOrderByJobId` |
| `GET` | `/api/v3/juspay/get-customer-auth-token` | `IPaymentV2Api` | `getAuthTokenForJuspayV3` |
| `GET` | `/daily/orderpl/v1/get` | `IPaymentApi` | `getOrderByJobIdDaily` |
| `GET` | `/payment/presentation/api/juspaywallets/v2/getCustomerAuthToken` | `IInAppUPIApi` | `clientAuthTokenV2` |
| `GET` | `/payment/presentation/api/juspaywallets/v2/getCustomerAuthToken` | `IPaymentApi` | `getAuthTokenForJuspayV2` |
| `GET` | `api/paylater/paytm/v1/isLinked` | `IPaymentApi` | `isPaytmPostPaidLinked` |
| `GET` | `api/v1/order-job/{order_id}/refund` | `IDashRefundDetailsApi` | `getDashRefundDetails` |
| `GET` | `api/v1/user/paytmwallet/check_balance` | `IPaymentApi` | `checkPaytmBalance` |
| `GET` | `api/v1/user/paytmwallet/sso_token` | `IPaymentApi` | `paytmSSOToken` |
| `GET` | `checkout-service/external/order/{orderId}/refundStatus` | `IRefundDetailsApi` | `getRefundDetails` |
| `GET` | `user/v1/transactions/refunds/active/count` | `a` | `a` |
| `PATCH` | `user/v1/transactions/refunds/ack` | `IRefundDetailsApi` | `updateRefundFeedback` |
| `POST` | `/api/v1/payment/presentation/client/callback/confirmTransaction` | `IDashPaymentApi` | `makeConfirmPayment` |
| `POST` | `/api/v1/scratch-card/assign` | `IRewardOfferApi` | `assignRewardOffer` |
| `POST` | `/api/v1/scratch-card/unlock` | `IRewardOfferApi` | `unlockRewardOffer` |
| `POST` | `/api/v2/json/track/card` | `b` | `c` |
| `POST` | `/api/v2/track/card` | `a` | `c` |
| `POST` | `/payment/presentation/v1/inappupi/update` | `IInAppUPIApi` | `saveGstResponse` |
| `POST` | `api/v1/cards/juspay` | `IPaymentApi` | `deleteCard` |
| `POST` | `api/v1/track/card` | `ISwiggyApi` | `getTrackCardList` |
| `POST` | `api/v2/order/confirm` | `IPaymentApi` | `confirmOrder` |

### Search & Discovery  (40)

| Method | Path | Interface | Fn |
|---|---|---|---|
| `GET` | `/api/v1/instamart/presearch` | `b` | `a` |
| `GET` | `/api/v1/instamart/search-config` | `a` | `a` |
| `GET` | `/api/v1/json/landing-page/{landing}` | `ILandingAPI` | `getFeatureCollectionJSON` |
| `GET` | `/api/v1/landing-page/{landing}` | `ILandingAPI` | `getFeatureCollection` |
| `GET` | `/api/v2/home/json` | `IDiscoveryJsonApi` | `getHomeListing` |
| `GET` | `/place/autocomplete` | `IPlacesSearchAPI` | `getGooglePlacesFromAutoComplete` |
| `GET` | `/place/autocomplete` | `ISwiggyPlacesSearchAPI` | `getGooglePlacesFromSwiggyPlaceAutoCompleteApi` |
| `GET` | `api/v1/instamart/auto_suggest` | `b` | `f` |
| `GET` | `api/v1/json/skeleton` | `IPageSkeletonAPI` | `getPageSkeletonDataJson` |
| `GET` | `api/v1/skeleton` | `IPageSkeletonAPI` | `getPageSkeletonData` |
| `POST` | `/api/v1/aggregated-entity/{pageIdentifier}` | `IAggregatedEntityAPI` | `getAggregatedEntityProto` |
| `POST` | `/api/v1/disliked` | `ILandingAPI` | `getHiddenRestos` |
| `POST` | `/api/v1/favourites` | `ILandingAPI` | `getFavorites` |
| `POST` | `/api/v1/food_bites_page` | `ILandingAPI` | `getFoodReelsData` |
| `POST` | `/api/v1/irctc` | `ILandingAPI` | `getIrctcData` |
| `POST` | `/api/v1/json/aggregated-entity/{pageIdentifier}` | `IAggregatedEntityAPI` | `getAggregatedEntityJson` |
| `POST` | `/api/v1/json/disliked` | `ILandingAPI` | `getHiddenRestoJson` |
| `POST` | `/api/v1/json/favourites` | `ILandingAPI` | `getFavoritesJson` |
| `POST` | `/api/v1/json/food_bites_page` | `ILandingAPI` | `getFoodReelsDataJson` |
| `POST` | `/api/v1/json/irctc` | `ILandingAPI` | `getIrctcDataJson` |
| `POST` | `/api/v1/json/landing-page/{landing}` | `ILandingAPI` | `getFeatureCollectionJSONWithRequestBody` |
| `POST` | `/api/v1/json/{pageID}` | `ISearchInlineAdsJsonApi` | `evaluatePageJson` |
| `POST` | `/api/v1/landing-page/{landing}` | `ILandingAPI` | `getFeatureCollectionWithRequestBody` |
| `POST` | `/api/v1/{pageID}` | `ISearchInlineAdsProtobufApi` | `evaluatePage` |
| `POST` | `/scenes/discovery/v1/event_user/profile_attribute/update` | `e` | `a` |
| `POST` | `api/search/suggest/v1` | `ISearchSuggestionsApi` | `getSearchSuggestions` |
| `POST` | `api/v1/ai-search/` | `ISearchResultsProtobufAPI` | `getAiSearchResults` |
| `POST` | `api/v1/ai-search/{tabId}` | `ISearchResultsProtobufAPI` | `getAiSearchResultsForTab` |
| `POST` | `api/v1/auto-suggest/{tabId}` | `ISearchSuggestionsProtobufAPI` | `getPLSearchSuggestions` |
| `POST` | `api/v1/json/ai-search/` | `ISearchResultsJsonApi` | `getAiSearchResults` |
| `POST` | `api/v1/json/ai-search/{tabId}` | `ISearchResultsJsonApi` | `getAiSearchResultsForTab` |
| `POST` | `api/v1/json/auto-suggest/{tabId}` | `ISearchSuggestionsJsonApi` | `getPLSearchSuggestions` |
| `POST` | `api/v1/json/unified-entity` | `IPageSkeletonAPI` | `getAggregatedPageSkeletonDataJSON` |
| `POST` | `api/v1/referrer/landing` | `IReferralApi` | `getReferralLandingScreenData` |
| `POST` | `api/v1/unified-entity` | `IPageSkeletonAPI` | `getAggregatedPageSkeletonData` |
| `POST` | `api/v2/launch` | `d` | `a` |
| `POST` | `api/v2/launch` | `e` | `a` |
| `POST` | `api/v2/referrer/landing` | `IReferralApi` | `getReferralLandingScreenDataForContactSync` |
| `POST` | `api/v3/json/search/{tabId}` | `ISearchResultsJsonApi` | `getSearchResults` |
| `POST` | `api/v3/search/{tabId}` | `ISearchResultsProtobufAPI` | `getSearchResults` |

### Support / Chat  (8)

| Method | Path | Interface | Fn |
|---|---|---|---|
| `GET` | `/api/v3/help/conversations?conversationStatus=open` | `IChatApi` | `getChatDetails` |
| `GET` | `/api/v4/help/conversations?conversationStatus=open` | `IChatV2Api` | `fetchActiveChats` |
| `GET` | `api/v2/help/conversations` | `g` | `a` |
| `GET` | `api/v3/help/conversations` | `g` | `c` |
| `GET` | `https://www.swiggy.com/mapi/help/resources` | `IHelpCenterAPI` | `getWebResourceList` |
| `POST` | `/api/v1/chat_bot` | `a` | `b` |
| `POST` | `/api/v1/json/chat_bot` | `a` | `a` |
| `POST` | `chat/v1/conversations/{conversationID}/messages` | `IChatNotificationApi` | `sendChatMessageApi` |

### User Profile & Consent  (16)

| Method | Path | Interface | Fn |
|---|---|---|---|
| `GET` | `/api/v1/delete/user_check` | `IProfileApi` | `deleteUserCheck` |
| `GET` | `/api/v1/getUserConsent` | `IUserConsentAPI` | `getUserConsent` |
| `GET` | `api/v3/user/profile` | `IProfileApi` | `refreshProfile` |
| `GET` | `api/v3/user/profile` | `h` | `refreshProfile` |
| `GET` | `api/v4/user/profile` | `IProfileApi` | `refreshProfileV4` |
| `GET` | `api/v4/user/profile` | `h` | `refreshProfileV4` |
| `POST` | `/api/v1/cloned-user/whitelist` | `IClonedAppWhiteListApi` | `requestForWhiteList` |
| `POST` | `/api/v1/cloned-user/whitelist` | `IClonedAppWhitelistJsonApi` | `requestForWhiteList` |
| `POST` | `/api/v1/delete/user` | `IProfileApi` | `deleteUser` |
| `POST` | `/api/v1/user/manage_consent` | `IProfileApi` | `manageConsent` |
| `POST` | `/api/v1/user/upcoming-bookings` | `a` | `a` |
| `POST` | `/api/v1/user/upcoming-bookings/json` | `a` | `b` |
| `POST` | `/message-set` | `a` | `a` |
| `PUT` | `/api/v1/userConsent` | `IUserConsentAPI` | `updateUserConsent` |
| `PUT` | `api/v1/profiling/attributes` | `ISignalAPI` | `callSignalAPI` |
| `PUT` | `api/v1/user/profile` | `h` | `d` |

## 4. Confirmed request payloads

Models resolved from the exact `@Body` type in each Retrofit method (obfuscated class names kept, since they are the real symbols).

### `POST /v1/token/refresh`

`IOzoneApi.java` → `refreshAccessToken` · model **b** (2 fields)

| JSON field | Type |
|---|---|
| `guest_access_token` | `String` |
| `refresh_token` | `String` |

### `POST api/v1/events/event-status`

`IMatchHoursAPI.java` → `fetchMultiEventStatus` · model **e** (1 fields)

| JSON field | Type |
|---|---|
| `user_id` | `String` |

### `POST api/search/suggest/v1`

`ISearchSuggestionsApi.java` → `getSearchSuggestions` · model **b** (1 fields)

| JSON field | Type |
|---|---|
| `categoryPage` | `String` |

### `POST api/v1/user/favorite`

`IFavouriteAPI.java` → `markFavourite` · model **o** (3 fields)

| JSON field | Type |
|---|---|
| `entity_id` | `String` |
| `entity_type` | `int` |
| `mark_favorite` | `boolean` |

### `POST api/v1/user/dislike`

`IDislikeApi.java` → `markDislike` · model **d** (2 fields)

| JSON field | Type |
|---|---|
| `entity_type` | `int` |
| `mark_dislike` | `boolean` |

### `POST api/v1/config/preLaunch`

`IPreLaunchAPI.java` → `getPreLaunchData` · model **PostablePreLaunchRequest** (1 fields)

| JSON field | Type |
|---|---|
| `appConfigList` | `List<String>` |

### `POST /api/v2/dynamicmenu/{restaurantId}`

`IMenuListingAPI.java` → `getDynamicMenuListing` · model **PostableMenuRequest** (24 fields)

| JSON field | Type |
|---|---|
| `appContext` | `String` |
| `collectionId` | `String` |
| `disableNearestOutletSelector` | `Boolean` |
| `flowContext` | `FlowContext` |
| `itemId` | `String` |
| `offerIds` | `String` |
| `corporatePasscode` | `String` |
| `preselected_tabs` | `String[]` |
| `qrEnabled` | `String` |
| `query` | `String` |
| `request_contexts` | `List<String>` |
| `searchGuidedFilters` | `Map<String, ? extends List<GuidedSearchFilter>>` |
| `searchMetaMap` | `Map<String, String>` |
| `searchSecondaryFilters` | `Map<String, ? extends List<Facet>>` |
| `isSld` | `boolean` |
| `restaurantSlug` | `String` |
| `source` | `String` |
| `sourceRequestId` | `String` |
| `sourceSessionId` | `String` |
| `subSource` | `String` |
| `submitAction` | `String` |
| `suggestType` | `String` |
| `suggestionTitle` | `String` |
| `takeaway` | `boolean` |

### `POST /api/v2/menu/{restaurantId}`

`IMenuListingAPI.java` → `getMenuListing` · model **PostableMenuRequest** (24 fields)

| JSON field | Type |
|---|---|
| `appContext` | `String` |
| `collectionId` | `String` |
| `disableNearestOutletSelector` | `Boolean` |
| `flowContext` | `FlowContext` |
| `itemId` | `String` |
| `offerIds` | `String` |
| `corporatePasscode` | `String` |
| `preselected_tabs` | `String[]` |
| `qrEnabled` | `String` |
| `query` | `String` |
| `request_contexts` | `List<String>` |
| `searchGuidedFilters` | `Map<String, ? extends List<GuidedSearchFilter>>` |
| `searchMetaMap` | `Map<String, String>` |
| `searchSecondaryFilters` | `Map<String, ? extends List<Facet>>` |
| `isSld` | `boolean` |
| `restaurantSlug` | `String` |
| `source` | `String` |
| `sourceRequestId` | `String` |
| `sourceSessionId` | `String` |
| `subSource` | `String` |
| `submitAction` | `String` |
| `suggestType` | `String` |
| `suggestionTitle` | `String` |
| `takeaway` | `boolean` |

### `POST /api/v2/resolve/menu/{restaurantName}`

`IMenuListingAPI.java` → `getResolveMenuListing` · model **PostableMenuRequest** (24 fields)

| JSON field | Type |
|---|---|
| `appContext` | `String` |
| `collectionId` | `String` |
| `disableNearestOutletSelector` | `Boolean` |
| `flowContext` | `FlowContext` |
| `itemId` | `String` |
| `offerIds` | `String` |
| `corporatePasscode` | `String` |
| `preselected_tabs` | `String[]` |
| `qrEnabled` | `String` |
| `query` | `String` |
| `request_contexts` | `List<String>` |
| `searchGuidedFilters` | `Map<String, ? extends List<GuidedSearchFilter>>` |
| `searchMetaMap` | `Map<String, String>` |
| `searchSecondaryFilters` | `Map<String, ? extends List<Facet>>` |
| `isSld` | `boolean` |
| `restaurantSlug` | `String` |
| `source` | `String` |
| `sourceRequestId` | `String` |
| `sourceSessionId` | `String` |
| `subSource` | `String` |
| `submitAction` | `String` |
| `suggestType` | `String` |
| `suggestionTitle` | `String` |
| `takeaway` | `boolean` |

### `POST /api/v1/menu/search/json`

`IMenuListingAPI.java` → `getSearchJsonListing` · model **PostableSearchRequest** (8 fields)

| JSON field | Type |
|---|---|
| `flowContext` | `FlowContext` |
| `query` | `String` |
| `restaurantIdOfAddedItem` | `String` |
| `sldEnabled` | `boolean` |
| `submitAction` | `String` |
| `suggestType` | `String` |
| `trackingId` | `String` |
| `vegFilter` | `Boolean` |

### `POST /api/v1/menu/search`

`IMenuListingAPI.java` → `getSearchListing` · model **PostableSearchRequest** (8 fields)

| JSON field | Type |
|---|---|
| `flowContext` | `FlowContext` |
| `query` | `String` |
| `restaurantIdOfAddedItem` | `String` |
| `sldEnabled` | `boolean` |
| `submitAction` | `String` |
| `suggestType` | `String` |
| `trackingId` | `String` |
| `vegFilter` | `Boolean` |

### `POST /api/v1/offer`

`IOffersApi.java` → `getOfferDetail` · model **PostableOfferRequest** (3 fields)

| JSON field | Type |
|---|---|
| `couponCode` | `String` |
| `offerIds` | `List<String>` |
| `offerType` | `String` |

### `POST /api/v1/instamart/user-preferences/update`

`IUserPreferenceApi.java` → `updateUserPreferences` · model **l** (1 fields)

| JSON field | Type |
|---|---|
| `location_context` | `d` |

### `POST /api/v1/instamart/pass/activate`

`IPassApi.java` → `activatePass` · model **b** (1 fields)

| JSON field | Type |
|---|---|
| `location_context` | `in.swiggy.android.tejas.im.userPrefrence.d` |

### `POST analytics/transactional/device/add/`

`ISpnsApi.java` → `registerDeviceSPNS` · model **j** (2 fields)

| JSON field | Type |
|---|---|
| `customerId` | `String` |
| `userType` | `String` |

### `POST /api/v1/app/screenshots/upload-urls`

`o.java` → `a` · model **i** (1 fields)

| JSON field | Type |
|---|---|
| `count` | `int` |

### `POST api/v2/launch`

`e.java` → `a` · model **PostableAggregatedLaunchRequest** (3 fields)

| JSON field | Type |
|---|---|
| `appConfigList` | `List<String>` |
| `dash` | `n` |
| `food` | `n` |

### `POST addresses/v1/nearby-eligible`

`c.java` → `a` · model **f** (2 fields)

| JSON field | Type |
|---|---|
| `radius_km` | `float` |
| `request_context` | `d` |

## 5. Notable payment / UPI surface

| Method | Path | Interface |
|---|---|---|
| `GET` | `api/v1/user/paytmwallet/check_balance` | `IPaymentApi` |
| `GET` | `api/v1/user/paytmwallet/sso_token` | `IPaymentApi` |
| `GET` | `api/paylater/paytm/v1/isLinked` | `IPaymentApi` |
| `POST` | `api/v2/order/confirm` | `IPaymentApi` |
| `POST` | `api/v1/cards/juspay` | `IPaymentApi` |
| `DELETE` | `payment/presentation/api/v1/upi/delete` | `IPaymentApi` |
| `GET` | `/payment/presentation/api/juspaywallets/v2/getCustomerAuthToken` | `IInAppUPIApi` |
| `POST` | `/payment/presentation/v1/inappupi/update` | `IInAppUPIApi` |
| `GET` | `/api/v3/juspay/get-customer-auth-token` | `IPaymentV2Api` |
| `DELETE` | `/payment/presentation/v1/refunds/clearNotification` | `IRefundsAPI` |
| `GET` | `/api/v1/dash/oms/order/{orderJobId}/context/ORDER_JOB` | `IDashPaymentApi` |
| `POST` | `/api/v1/payment/presentation/client/callback/confirmTransaction` | `IDashPaymentApi` |

Payment stack includes **Juspay HyperSDK** (in-app UPI), **NPCI UPI PIN activity component** (`org.npci.upi.security`), Paytm postpaid/wallet, Amazon Pay, PhonePe. Juspay app-list in `assets/juspay/config.json`.

## 6. Endpoints NOT in the Retrofit inventory

These appear only as string literals / other HTTP layers:

- `https://www.swiggy.com/mapi/help/resources` — help content
- `https://disc.swiggy.com/api/v2/launch` and `/connect` — device/attribution bootstrap
- `https://analytics.swiggy.com` · `https://spns.swiggy.com`
- `POST topics/aws.msk.bureau.androidDeviceEvents` — Kafka topic (Bureau device risk)
- `POST v1/deviceService/deviceData/android`
- `POST analytics/transactional/device/add/`
- `POST api/v1/app/screenshots/upload-urls` — screenshot upload
- `GET /place/autocomplete` (Google Places proxy)
## 7. Limits of this analysis

- Static only — **no request was executed**; runtime base URLs, auth flows and actual payload values were not observed.
- Base host per service comes from runtime DI config; the mapping service→host is inferred from names, not proven.
- Obfuscated class names (`a`, `b`, `n`…) are kept verbatim — they are the real symbols in this build.
- Response models are large (50+ linked); only request payloads and notable responses are tabulated here.
- Google/Firebase/Crashlytics/Juspay SDK internals were inventoried but are third-party, not Swiggy API surface.