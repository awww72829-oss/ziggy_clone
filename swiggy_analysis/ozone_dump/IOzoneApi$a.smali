.class public final Lin/swiggy/android/tejas/ozone/api/IOzoneApi$a;
.super Ljava/lang/Object;
.source "SourceFile"


# annotations
.annotation system Ldalvik/annotation/EnclosingClass;
    value = Lin/swiggy/android/tejas/ozone/api/IOzoneApi;
.end annotation

.annotation system Ldalvik/annotation/InnerClass;
    accessFlags = 0x19
    name = "a"
.end annotation


# static fields
.field static final synthetic $$INSTANCE:Lin/swiggy/android/tejas/ozone/api/IOzoneApi$a;

.field private static final REFRESH_ACCESS_TOKEN_API:Ljava/lang/String; = "/v1/token/refresh"
    .annotation build Lorg/jetbrains/annotations/NotNull;
    .end annotation
.end field

.field private static final SIGN_IN_WITH_TID_API:Ljava/lang/String; = "/v1/accounts/signInWithTID"
    .annotation build Lorg/jetbrains/annotations/NotNull;
    .end annotation
.end field


# direct methods
.method static constructor <clinit>()V
    .locals 1

    new-instance v0, Lin/swiggy/android/tejas/ozone/api/IOzoneApi$a;

    invoke-direct {v0}, Lin/swiggy/android/tejas/ozone/api/IOzoneApi$a;-><init>()V

    sput-object v0, Lin/swiggy/android/tejas/ozone/api/IOzoneApi$a;->$$INSTANCE:Lin/swiggy/android/tejas/ozone/api/IOzoneApi$a;

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
