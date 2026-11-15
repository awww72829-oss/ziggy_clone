.class public final Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;
.super Ljava/lang/Object;
.source "SourceFile"


# annotations
.annotation system Ldalvik/annotation/MemberClasses;
    value = {
        Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload$$serializer;,
        Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload$Companion;
    }
.end annotation

.annotation runtime Lkotlin/Metadata;
    d1 = {
        "\u0000\u000c\n\u0002\u0018\u0002\n\u0002\u0010\u0000\n\u0002\u0008\u0003\u0008\u0087\u0008\u0018\u0000 \u00022\u00020\u0001:\u0002\u0003\u0002\u00a8\u0006\u0004"
    }
    d2 = {
        "Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;",
        "",
        "Companion",
        "$serializer",
        "swiggylynx"
    }
    k = 0x1
    mv = {
        0x2,
        0x2,
        0x0
    }
    xi = 0x30
.end annotation

.annotation runtime Lkotlinx/serialization/g;
.end annotation


# static fields
.field public static final Companion:Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload$Companion;
    .annotation build Lorg/jetbrains/annotations/NotNull;
    .end annotation
.end field


# instance fields
.field public final a:Z

.field public final b:Ljava/lang/String;


# direct methods
.method static constructor <clinit>()V
    .locals 1

    .line 1
    new-instance v0, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload$Companion;

    .line 2
    .line 3
    invoke-direct {v0}, Ljava/lang/Object;-><init>()V

    .line 4
    .line 5
    .line 6
    sput-object v0, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;->Companion:Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload$Companion;

    .line 7
    .line 8
    return-void
.end method

.method public synthetic constructor <init>(ILjava/lang/String;Z)V
    .locals 3

    .line 1
    and-int/lit8 v0, p1, 0x1

    .line 2
    .line 3
    const/4 v1, 0x0

    .line 4
    const/4 v2, 0x1

    .line 5
    if-ne v2, v0, :cond_1

    .line 6
    .line 7
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    .line 8
    .line 9
    .line 10
    iput-boolean p3, p0, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;->a:Z

    .line 11
    .line 12
    and-int/lit8 p1, p1, 0x2

    .line 13
    .line 14
    if-nez p1, :cond_0

    .line 15
    .line 16
    iput-object v1, p0, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;->b:Ljava/lang/String;

    .line 17
    .line 18
    return-void

    .line 19
    :cond_0
    iput-object p2, p0, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;->b:Ljava/lang/String;

    .line 20
    .line 21
    return-void

    .line 22
    :cond_1
    sget-object p0, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload$$serializer;->INSTANCE:Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload$$serializer;

    .line 23
    .line 24
    invoke-virtual {p0}, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload$$serializer;->getDescriptor()Lkotlinx/serialization/descriptors/SerialDescriptor;

    .line 25
    .line 26
    .line 27
    move-result-object p0

    .line 28
    invoke-static {p1, v2, p0}, Lkotlinx/serialization/internal/z1;->b(IILkotlinx/serialization/descriptors/SerialDescriptor;)V

    .line 29
    .line 30
    .line 31
    throw v1
.end method

.method public constructor <init>(ZLjava/lang/String;)V
    .locals 0

    .line 32
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    .line 33
    iput-boolean p1, p0, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;->a:Z

    .line 34
    iput-object p2, p0, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;->b:Ljava/lang/String;

    return-void
.end method


# virtual methods
.method public final equals(Ljava/lang/Object;)Z
    .locals 4

    const/4 v0, 0x1

    if-ne p0, p1, :cond_0

    return v0

    :cond_0
    instance-of v1, p1, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;

    const/4 v2, 0x0

    if-nez v1, :cond_1

    return v2

    :cond_1
    check-cast p1, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;

    iget-boolean v1, p0, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;->a:Z

    iget-boolean v3, p1, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;->a:Z

    if-eq v1, v3, :cond_2

    return v2

    :cond_2
    iget-object p0, p0, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;->b:Ljava/lang/String;

    iget-object p1, p1, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;->b:Ljava/lang/String;

    invoke-static {p0, p1}, Lkotlin/jvm/internal/Intrinsics;->e(Ljava/lang/Object;Ljava/lang/Object;)Z

    move-result p0

    if-nez p0, :cond_3

    return v2

    :cond_3
    return v0
.end method

.method public final hashCode()I
    .locals 1

    iget-boolean v0, p0, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;->a:Z

    invoke-static {v0}, Ljava/lang/Boolean;->hashCode(Z)I

    move-result v0

    mul-int/lit8 v0, v0, 0x1f

    iget-object p0, p0, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;->b:Ljava/lang/String;

    if-nez p0, :cond_0

    const/4 p0, 0x0

    goto :goto_0

    :cond_0
    invoke-virtual {p0}, Ljava/lang/String;->hashCode()I

    move-result p0

    :goto_0
    add-int/2addr v0, p0

    return v0
.end method

.method public final toString()Ljava/lang/String;
    .locals 4

    .line 1
    const-string v0, ", accessToken="

    .line 2
    .line 3
    const-string v1, ")"

    .line 4
    .line 5
    const-string v2, "UpdateAccessTokenResponsePayload(isUpdateFailed="

    .line 6
    .line 7
    iget-object v3, p0, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;->b:Ljava/lang/String;

    .line 8
    .line 9
    iget-boolean p0, p0, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;->a:Z

    .line 10
    .line 11
    invoke-static {v2, v0, v3, p0, v1}, Lcom/google/android/gms/internal/ads/a;->h(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;ZLjava/lang/String;)Ljava/lang/String;

    .line 12
    .line 13
    .line 14
    move-result-object p0

    .line 15
    return-object p0
.end method
