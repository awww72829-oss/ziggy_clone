.class public final Lin/swiggy/android/tejas/ozone/api/IInAppUPIApi$a;
.super Ljava/lang/Object;
.source "SourceFile"


# annotations
.annotation system Ldalvik/annotation/EnclosingClass;
    value = Lin/swiggy/android/tejas/ozone/api/IInAppUPIApi;
.end annotation

.annotation system Ldalvik/annotation/InnerClass;
    accessFlags = 0x19
    name = "a"
.end annotation


# static fields
.field static final synthetic $$INSTANCE:Lin/swiggy/android/tejas/ozone/api/IInAppUPIApi$a;

.field private static final GET_CLIENT_AUTH_TOKEN_V2:Ljava/lang/String; = "/payment/presentation/api/juspaywallets/v2/getCustomerAuthToken"
    .annotation build Lorg/jetbrains/annotations/NotNull;
    .end annotation
.end field

.field private static final SAVE_GST_RESPONSE:Ljava/lang/String; = "/payment/presentation/v1/inappupi/update"
    .annotation build Lorg/jetbrains/annotations/NotNull;
    .end annotation
.end field


# direct methods
.method static constructor <clinit>()V
    .locals 1

    new-instance v0, Lin/swiggy/android/tejas/ozone/api/IInAppUPIApi$a;

    invoke-direct {v0}, Lin/swiggy/android/tejas/ozone/api/IInAppUPIApi$a;-><init>()V

    sput-object v0, Lin/swiggy/android/tejas/ozone/api/IInAppUPIApi$a;->$$INSTANCE:Lin/swiggy/android/tejas/ozone/api/IInAppUPIApi$a;

    return-void
.end method

.method private constructor <init>()V
    .locals 0

    .line 1
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    .line 2
    .line 3
    .line 4
    return-void
.end method
