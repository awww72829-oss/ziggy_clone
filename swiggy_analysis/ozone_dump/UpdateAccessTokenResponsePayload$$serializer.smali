.class public final synthetic Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload$$serializer;
.super Ljava/lang/Object;
.source "SourceFile"

# interfaces
.implements Lkotlinx/serialization/internal/f0;


# annotations
.annotation system Ldalvik/annotation/EnclosingClass;
    value = Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;
.end annotation

.annotation system Ldalvik/annotation/InnerClass;
    accessFlags = 0x1019
    name = "$serializer"
.end annotation

.annotation system Ldalvik/annotation/Signature;
    value = {
        "Ljava/lang/Object;",
        "Lkotlinx/serialization/internal/f0;"
    }
.end annotation

.annotation runtime Lkotlin/Metadata;
    d1 = {
        "\u0000:\n\u0000\n\u0002\u0018\u0002\n\u0002\u0018\u0002\n\u0002\u0008\u0002\n\u0002\u0018\u0002\n\u0002\u0008\u0002\n\u0002\u0010\u0002\n\u0002\u0008\u0002\n\u0002\u0018\u0002\n\u0002\u0008\u0003\n\u0002\u0010\u0011\n\u0002\u0018\u0002\n\u0002\u0008\u0002\n\u0002\u0018\u0002\n\u0002\u0008\u0005\u0008\u00c7\u0002\u0018\u00002\u0008\u0012\u0004\u0012\u00020\u00020\u0001B\t\u0008\u0002\u00a2\u0006\u0004\u0008\u0003\u0010\u0004J\u001d\u0010\t\u001a\u00020\u00082\u0006\u0010\u0006\u001a\u00020\u00052\u0006\u0010\u0007\u001a\u00020\u0002\u00a2\u0006\u0004\u0008\t\u0010\nJ\u0015\u0010\r\u001a\u00020\u00022\u0006\u0010\u000c\u001a\u00020\u000b\u00a2\u0006\u0004\u0008\r\u0010\u000eJ\u0017\u0010\u0011\u001a\u000c\u0012\u0008\u0012\u0006\u0012\u0002\u0008\u00030\u00100\u000f\u00a2\u0006\u0004\u0008\u0011\u0010\u0012R\u0017\u0010\u0014\u001a\u00020\u00138\u0006\u00a2\u0006\u000c\n\u0004\u0008\u0014\u0010\u0015\u001a\u0004\u0008\u0016\u0010\u0017\u00a8\u0006\u0018"
    }
    d2 = {
        "in/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload.$serializer",
        "Lkotlinx/serialization/internal/f0;",
        "Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;",
        "<init>",
        "()V",
        "Lkotlinx/serialization/encoding/Encoder;",
        "encoder",
        "value",
        "",
        "serialize",
        "(Lkotlinx/serialization/encoding/Encoder;Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;)V",
        "Lkotlinx/serialization/encoding/Decoder;",
        "decoder",
        "deserialize",
        "(Lkotlinx/serialization/encoding/Decoder;)Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;",
        "",
        "Lkotlinx/serialization/KSerializer;",
        "childSerializers",
        "()[Lkotlinx/serialization/KSerializer;",
        "Lkotlinx/serialization/descriptors/SerialDescriptor;",
        "descriptor",
        "Lkotlinx/serialization/descriptors/SerialDescriptor;",
        "getDescriptor",
        "()Lkotlinx/serialization/descriptors/SerialDescriptor;",
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

.annotation runtime Lkotlin/d;
.end annotation


# static fields
.field public static final INSTANCE:Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload$$serializer;
    .annotation build Lorg/jetbrains/annotations/NotNull;
    .end annotation
.end field

.field private static final descriptor:Lkotlinx/serialization/descriptors/SerialDescriptor;
    .annotation build Lorg/jetbrains/annotations/NotNull;
    .end annotation
.end field


# direct methods
.method static constructor <clinit>()V
    .locals 4

    .line 1
    new-instance v0, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload$$serializer;

    .line 2
    .line 3
    invoke-direct {v0}, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload$$serializer;-><init>()V

    .line 4
    .line 5
    .line 6
    sput-object v0, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload$$serializer;->INSTANCE:Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload$$serializer;

    .line 7
    .line 8
    new-instance v1, Lkotlinx/serialization/internal/k1;

    .line 9
    .line 10
    const-string v2, "in.swiggy.android.swiggylynx.plugin.ozone.response.UpdateAccessTokenResponsePayload"

    .line 11
    .line 12
    const/4 v3, 0x2

    .line 13
    invoke-direct {v1, v2, v0, v3}, Lkotlinx/serialization/internal/k1;-><init>(Ljava/lang/String;Lkotlinx/serialization/internal/f0;I)V

    .line 14
    .line 15
    .line 16
    const-string v0, "isUpdateFailed"

    .line 17
    .line 18
    const/4 v2, 0x0

    .line 19
    invoke-virtual {v1, v0, v2}, Lkotlinx/serialization/internal/k1;->k(Ljava/lang/String;Z)V

    .line 20
    .line 21
    .line 22
    const-string v0, "x-oztok"

    .line 23
    .line 24
    const/4 v2, 0x1

    .line 25
    invoke-virtual {v1, v0, v2}, Lkotlinx/serialization/internal/k1;->k(Ljava/lang/String;Z)V

    .line 26
    .line 27
    .line 28
    sput-object v1, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload$$serializer;->descriptor:Lkotlinx/serialization/descriptors/SerialDescriptor;

    .line 29
    .line 30
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


# virtual methods
.method public final childSerializers()[Lkotlinx/serialization/KSerializer;
    .locals 3
    .annotation system Ldalvik/annotation/Signature;
        value = {
            "()[",
            "Lkotlinx/serialization/KSerializer;"
        }
    .end annotation

    .annotation build Lorg/jetbrains/annotations/NotNull;
    .end annotation

    .line 1
    sget-object p0, Lkotlinx/serialization/internal/y1;->a:Lkotlinx/serialization/internal/y1;

    .line 2
    .line 3
    invoke-static {p0}, Lkotlin/jvm/internal/u;->w(Lkotlinx/serialization/KSerializer;)Lkotlinx/serialization/KSerializer;

    .line 4
    .line 5
    .line 6
    move-result-object p0

    .line 7
    const/4 v0, 0x2

    .line 8
    new-array v0, v0, [Lkotlinx/serialization/KSerializer;

    .line 9
    .line 10
    sget-object v1, Lkotlinx/serialization/internal/h;->a:Lkotlinx/serialization/internal/h;

    .line 11
    .line 12
    const/4 v2, 0x0

    .line 13
    aput-object v1, v0, v2

    .line 14
    .line 15
    const/4 v1, 0x1

    .line 16
    aput-object p0, v0, v1

    .line 17
    .line 18
    return-object v0
.end method

.method public final deserialize(Lkotlinx/serialization/encoding/Decoder;)Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;
    .locals 9
    .param p1    # Lkotlinx/serialization/encoding/Decoder;
        .annotation build Lorg/jetbrains/annotations/NotNull;
        .end annotation
    .end param
    .annotation build Lorg/jetbrains/annotations/NotNull;
    .end annotation

    .line 1
    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 2
    .line 3
    .line 4
    sget-object p0, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload$$serializer;->descriptor:Lkotlinx/serialization/descriptors/SerialDescriptor;

    .line 5
    .line 6
    invoke-interface {p1, p0}, Lkotlinx/serialization/encoding/Decoder;->b(Lkotlinx/serialization/descriptors/SerialDescriptor;)Lkotlinx/serialization/encoding/a;

    .line 7
    .line 8
    .line 9
    move-result-object p1

    .line 10
    const/4 v0, 0x1

    .line 11
    const/4 v1, 0x0

    .line 12
    const/4 v2, 0x0

    .line 13
    move v3, v0

    .line 14
    move v4, v1

    .line 15
    move v5, v4

    .line 16
    move-object v6, v2

    .line 17
    :goto_0
    if-eqz v3, :cond_3

    .line 18
    .line 19
    invoke-interface {p1, p0}, Lkotlinx/serialization/encoding/a;->o(Lkotlinx/serialization/descriptors/SerialDescriptor;)I

    .line 20
    .line 21
    .line 22
    move-result v7

    .line 23
    const/4 v8, -0x1

    .line 24
    if-eq v7, v8, :cond_2

    .line 25
    .line 26
    if-eqz v7, :cond_1

    .line 27
    .line 28
    if-ne v7, v0, :cond_0

    .line 29
    .line 30
    sget-object v7, Lkotlinx/serialization/internal/y1;->a:Lkotlinx/serialization/internal/y1;

    .line 31
    .line 32
    invoke-interface {p1, p0, v0, v7, v6}, Lkotlinx/serialization/encoding/a;->n(Lkotlinx/serialization/descriptors/SerialDescriptor;ILkotlinx/serialization/b;Ljava/lang/Object;)Ljava/lang/Object;

    .line 33
    .line 34
    .line 35
    move-result-object v6

    .line 36
    check-cast v6, Ljava/lang/String;

    .line 37
    .line 38
    or-int/lit8 v4, v4, 0x2

    .line 39
    .line 40
    goto :goto_0

    .line 41
    :cond_0
    invoke-static {v7}, Lin/swiggy/android/commonsui/exoplayerpool/e;->e(I)V

    .line 42
    .line 43
    .line 44
    return-object v2

    .line 45
    :cond_1
    invoke-interface {p1, p0, v1}, Lkotlinx/serialization/encoding/a;->z(Lkotlinx/serialization/descriptors/SerialDescriptor;I)Z

    .line 46
    .line 47
    .line 48
    move-result v5

    .line 49
    or-int/lit8 v4, v4, 0x1

    .line 50
    .line 51
    goto :goto_0

    .line 52
    :cond_2
    move v3, v1

    .line 53
    goto :goto_0

    .line 54
    :cond_3
    invoke-interface {p1, p0}, Lkotlinx/serialization/encoding/a;->c(Lkotlinx/serialization/descriptors/SerialDescriptor;)V

    .line 55
    .line 56
    .line 57
    new-instance p0, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;

    .line 58
    .line 59
    invoke-direct {p0, v4, v6, v5}, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;-><init>(ILjava/lang/String;Z)V

    .line 60
    .line 61
    .line 62
    return-object p0
.end method

.method public bridge synthetic deserialize(Lkotlinx/serialization/encoding/Decoder;)Ljava/lang/Object;
    .locals 0

    .line 63
    invoke-virtual {p0, p1}, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload$$serializer;->deserialize(Lkotlinx/serialization/encoding/Decoder;)Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;

    move-result-object p0

    return-object p0
.end method

.method public final getDescriptor()Lkotlinx/serialization/descriptors/SerialDescriptor;
    .locals 0
    .annotation build Lorg/jetbrains/annotations/NotNull;
    .end annotation

    sget-object p0, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload$$serializer;->descriptor:Lkotlinx/serialization/descriptors/SerialDescriptor;

    return-object p0
.end method

.method public final serialize(Lkotlinx/serialization/encoding/Encoder;Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;)V
    .locals 2
    .param p1    # Lkotlinx/serialization/encoding/Encoder;
        .annotation build Lorg/jetbrains/annotations/NotNull;
        .end annotation
    .end param
    .param p2    # Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;
        .annotation build Lorg/jetbrains/annotations/NotNull;
        .end annotation
    .end param

    .line 1
    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 2
    .line 3
    .line 4
    invoke-virtual {p2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 5
    .line 6
    .line 7
    sget-object p0, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload$$serializer;->descriptor:Lkotlinx/serialization/descriptors/SerialDescriptor;

    .line 8
    .line 9
    invoke-interface {p1, p0}, Lkotlinx/serialization/encoding/Encoder;->b(Lkotlinx/serialization/descriptors/SerialDescriptor;)Lkotlinx/serialization/encoding/b;

    .line 10
    .line 11
    .line 12
    move-result-object p1

    .line 13
    iget-boolean v0, p2, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;->a:Z

    .line 14
    .line 15
    iget-object p2, p2, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;->b:Ljava/lang/String;

    .line 16
    .line 17
    const/4 v1, 0x0

    .line 18
    invoke-interface {p1, p0, v1, v0}, Lkotlinx/serialization/encoding/b;->z(Lkotlinx/serialization/descriptors/SerialDescriptor;IZ)V

    .line 19
    .line 20
    .line 21
    invoke-interface {p1, p0}, Lkotlinx/serialization/encoding/b;->p(Lkotlinx/serialization/descriptors/SerialDescriptor;)Z

    .line 22
    .line 23
    .line 24
    move-result v0

    .line 25
    if-eqz v0, :cond_0

    .line 26
    .line 27
    goto :goto_0

    .line 28
    :cond_0
    if-eqz p2, :cond_1

    .line 29
    .line 30
    :goto_0
    sget-object v0, Lkotlinx/serialization/internal/y1;->a:Lkotlinx/serialization/internal/y1;

    .line 31
    .line 32
    const/4 v1, 0x1

    .line 33
    invoke-interface {p1, p0, v1, v0, p2}, Lkotlinx/serialization/encoding/b;->j(Lkotlinx/serialization/descriptors/SerialDescriptor;ILkotlinx/serialization/h;Ljava/lang/Object;)V

    .line 34
    .line 35
    .line 36
    :cond_1
    invoke-interface {p1, p0}, Lkotlinx/serialization/encoding/b;->c(Lkotlinx/serialization/descriptors/SerialDescriptor;)V

    .line 37
    .line 38
    .line 39
    return-void
.end method

.method public bridge synthetic serialize(Lkotlinx/serialization/encoding/Encoder;Ljava/lang/Object;)V
    .locals 0

    .line 40
    check-cast p2, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;

    invoke-virtual {p0, p1, p2}, Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload$$serializer;->serialize(Lkotlinx/serialization/encoding/Encoder;Lin/swiggy/android/swiggylynx/plugin/ozone/response/UpdateAccessTokenResponsePayload;)V

    return-void
.end method

.method public bridge typeParametersSerializers()[Lkotlinx/serialization/KSerializer;
    .locals 0
    .annotation system Ldalvik/annotation/Signature;
        value = {
            "()[",
            "Lkotlinx/serialization/KSerializer;"
        }
    .end annotation

    .annotation build Lorg/jetbrains/annotations/NotNull;
    .end annotation

    .line 1
    sget-object p0, Lkotlinx/serialization/internal/l1;->a:[Lkotlinx/serialization/KSerializer;

    .line 2
    .line 3
    return-object p0
.end method
