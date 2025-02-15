import torch
import torch.nn as nn
import math

class InputEmbeddings(nn.Module):
  def __init__(self, d_model: int,vocab_size :int): #d_model-dimensionality of the model,vocab_size --> total vocabulary
    super().__init__()
    self.d_model=d_model
    self.vocab_size=vocab_size
    self.embedding=nn.Embedding(vocab_size,d_model)

  def forward(self,x):
    return self.embedding(x)*math.sqrt(self.d_model)

class PositionalEncoding(nn.Module):
  def __init__(self,d_model:int,seq_len:int,dropout:float):
    self.d_model=d_model
    self.seq_len=seq_len
    self.dropout=nn.Dropout(dropout)


    pe=torch.zeros(self.seq_len,self.d_model) #create a 0x0 matrix
    position=torch.arange(0,seq_len,dtype=torch.float).unsqueeze(1) #creating [0...seq_Len]-->[seq_len,1]
    div_term=torch.exp(torch.arange(0,d_model,2).float()*(-math.log(10000.0)/d_model))
    pe[:,0::2]=torch.sin(position*div_term) # apply sin to even
    pe[:,1::2]=torch.cos(position*div_term)# apply cos to odd
    pe=pe.unsqueeze(0) # adding a new dimension batch dim --->[1,seq_len,d_model]
    self.register_buffer('pe',pe) #to be saved as a file

def forward(self,x):
  x= x + (self.pe[:,:x.shape[1],: ]).require_grad_(False) # False cause no need to back prop.
  return self.dropout(x)

class LayerNormalization(nn.Module):
  def __init__(self,eps:float=10**-6):
    super().__init__()
    self.eps=eps #helps if std. is close to zero
    self.alpha=nn.Parameter(torch.ones(1))
    self.beta=nn.Parameter(torch.zeros(1))

  def forward(self,x):
    mean=x.float().mean(-1,keepdim=True)#layer norm so row wise normalization,normalize each training example seperately.
    std=x.float().std(-1,keepdim=True)
    return self.alpha*(x-mean)/(std+self.eps)+self.beta


class FeedForwardlock(nn.Module): # higher dims MLP, which helps transformer to analyse info after self attension.
   def __init__(self,d_model:int,d_ff:int,dropout:float):
     super().__init__()
     self.linear_1=nn.Linear(d_model,d_ff)
     self.dropout=nn.Dropout(dropout)
     self.linear_2=nn.Linear(d_ff,d_model)

   def forward(self,x):

    return self.linear_2(self.dropout(torch.relu(self.linear_1(x))))


class MultiHeadAttentionBlock(nn.Module):
  def __init__(self,d_model:int,h:int,dropout:float): #h--> number of heads
    super().__init__()
    self.d_model=d_model
    self.h=h
    assert d_model % h==0,"d_model must be divisible by h"
    self.d_k=d_model//h  #head size
    self.w_q=nn.Linear(d_model,d_model) 
    self.w_k=nn.Linear(d_model,d_model)
    self.w_v=nn.Linear(d_model,d_model)
    self.w_o=nn.Linear(d_model,d_model)
    self.dropout=nn.Dropout(dropout)

  @staticmethod
  def attention(query, key, value, mask, dropout: nn.Dropout):
    d_k = query.shape[-1]
        # Just apply the formula from the paper
        # (batch, h, seq_len, d_k) --> (batch, h, seq_len, seq_len)
    attention_scores = (query @ key.transpose(-2, -1)) / math.sqrt(d_k)
    if mask is not None:
            # Write a very low value (indicating -inf) to the positions where mask == 0
      attention_scores.masked_fill_(mask == 0, -1e9)
    attention_scores = attention_scores.softmax(dim=-1) # (batch, h, seq_len, seq_len) # Apply softmax
    if dropout is not None:
      attention_scores = dropout(attention_scores)
        # (batch, h, seq_len, seq_len) --> (batch, h, seq_len, d_k)
        # return attention scores which can be used for visualization
    return (attention_scores @ value), attention_scores

  def forward(self,q,k,v,mask):
    query=self.w_q(q)
    key=self.w_k(k)
    value=self.w_v(v)
    query=query.view(query.shape[0],query.shape[1],self.h,self.d_k).transpose(1,2 )#--->(b,h,seq,d_k)
    key=key.view(key.shape[0],key.shape[1],self.h,self.d_k).transpose(1,2)
    value=value.view(key.shape[0],value.shape[1],self.h,self.d_k).transpose(1,2)

    # Calculate attention
    x, self.attention_scores = MultiHeadAttentionBlock.attention(query, key, value, mask, self.dropout)

    # Combine all the heads together
    # (batch, h, seq_len, d_k) --> (b/atch, seq_len, h, d_k) --> (batch, seq_len, d_model)
    x = x.transpose(1, 2).contiguous().view(x.shape[0], -1, self.h * self.d_k)

    # Multiply by Wo
    # (batch, seq_len, d_model) --> (batch, seq_len, d_model)
    return self.w_o(x)

class ResidualConnection(nn.Module):
  def __init__ (self,features:int,dropout:int):
    super().__init__()
    self.dropout=nn.Dropout(dropout)
    self.norm=LayerNormalization(features)

  def forward(self,x,sublayer): #x+sublayer(x) for direct gradient distribution when backward prop
    return x + self.dropout(sublayer(self.norm(x)))

class EncoderBlock(nn.Module):
  def __init__(self,self_attention_block:MultiHeadAttentionBlock,feed_forward_block:FeedForwardlock,dropout:float):
    super().__init__()
    self.self_attension_block=self_attention_block
    self.feed_forward_block=feed_forward_block
    self.residual_connections=nn.ModuleList([LayerNormalization() for _ in range(2)])#modulelist - way to organise list of models
    

  def forward(self,x,src_mask):
    x = self.residual_connections[0](x,lambda x: self.self_attension_block(x,x,x,src_mask))
    x = self.residual_connections[1](x,self.feed_forward_block)
    return x


class Encoder(nn.Module):
  def __init__ (self,features:int,layers=nn.ModuleList):
    super().__init__()
    self.layers=layers
    self.norm=LayerNormalization(features)


  def forward(self,x,mask):
    for layers in self.layers:
      x=layers(x,mask) # output of the first layer is input of the the other
    return self.norm(x)

class DecoderBlock(nn.Module):
  def __init__ (self,features:int,self_attention_block:MultiHeadAttentionBlock,cross_attention_block:MultiHeadAttentionBlock,feed_forward_block:FeedForwardlock,dropout:float):
    super().__init__()
    self.self_attention_block=self_attention_block
    self.cross_attention_block=cross_attention_block
    self.feed_forward_block=FeedForwardlock
    self.dropout=nn.Dropout(dropout)
    self.residual_connections=nn.ModuleList([LayerNormalization() for _ in range(3)])

  def forward(self,x,encoder_output,src_mask,tgt_mask):
    x=self.residual_connections[0](x,lambda x: self.self_attention_block(x,x,x,tgt_mask))
    x=self.residual_connections[1](x,lambda x: self.cross_attention_block(x,encoder_output,encoder_output,src_mask))
    x=self.residual_connections[2](x,self.feed_forward_block)
    return x


class Decoder(nn.Module):
  def __init__(self,features:int,layers:nn.ModuleList):
    super().__init__()
    self.layers=layers
    self.norm=LayerNormalization(features)

  def forward(self,x,encoder_output,src_mask,tgt_mask):
    for layer in self.layers:
      x=layer(x,encoder_output,src_mask,tgt_mask)
    return self.norm(x)

class ProjectionLayer(nn.Module):
  def __init__(self,d_model,vocab_size):
    super().__init__()
    self.proj=nn.Linear(d_model,vocab_size) #--seq_len,d_model--->seq_len,Vocab_size 

  def forward(self,x):
    return torch.log_softmax(self.proj(x),dim=-1) 

class TransformerBlock(nn.Module):
  def __init__(self,encoder:Encoder,decoder:Decoder, src_embed: InputEmbeddings, tgt_embed: InputEmbeddings, src_pos: PositionalEncoding, tgt_pos: PositionalEncoding, projection_layer: ProjectionLayer):
    super().__init__()
    self.encoder = encoder
    self.decoder = decoder
    self.src_embed = src_embed
    self.tgt_embed = tgt_embed
    self.src_pos = src_pos
    self.tgt_pos = tgt_pos
    self.projection_layer = projection_layer

  def encode(self,src,src_mask):
    src=self.src_embed(src)
    src=self.src_pos(src)
    return self.encoder(src,src_mask)

  def decode(self,encoder_output:torch.tensor,src_mask:torch.tensor,tgt:torch.tensor,tgt_mask:torch.tensor):
    tgt=self.tgt_embed(tgt)
    tgt=self.tgt_pos(tgt)
    return self.decoder(tgt,encoder_output,src_mask,tgt_mask)

  def project(self,x):
    return self.projection_layer(x)


def BuildTransformer(src_vocab_size:int,tgt_vocab_size:int,src_seq_len:int,tgt_seq_len:int,d_model:int=512,N:int=6,h:int=8,dropout:float=0.1,d_ff:int=2048):
  #input embeddings
  src_embed=InputEmbeddings(d_model,src_vocab_size)
  tgt_embed=InputEmbeddings(d_model,tgt_vocab_size)
  
  #create positional embeddings
  src_pos=PositionalEncoding(d_model,src_seq_len,dropout)
  tgt_pos=PositionalEncoding(d_model,tgt_seq_len,dropout)

  #encoder
  encoder_blocks=[]
  for _ in range(N):
    encoder_self_attention_block=MultiHeadAttentionBlock(d_model,h,dropout)
    feed_forward_block=FeedForwardlock(d_model,d_ff,dropout)
    encoder_block = EncoderBlock(d_model, encoder_self_attention_block, feed_forward_block, dropout)
    encoder_blocks.append(encoder_block)
  

  #decoder
  decoder_blocks=[]
  for _ in range(N):
    decoder_self_attention_block=MultiHeadAttentionBlock(d_model,h,dropout)
    decoder_cross_attention_block=MultiHeadAttentionBlock(d_model,h,dropout)
    feed_forward_block=FeedForwardlock(d_model,d_ff,dropout)
    decoder_block = DecoderBlock(d_model, decoder_self_attention_block, decoder_cross_attention_block, feed_forward_block, dropout)
    decoder_blocks.append(decoder_block)
  encoder = Encoder(d_model, nn.ModuleList(encoder_blocks))
  decoder = Decoder(d_model, nn.ModuleList(decoder_blocks))

  projection_layer = ProjectionLayer(d_model, tgt_vocab_size)

  transformer = Transformer(encoder, decoder, src_embed, tgt_embed, src_pos, tgt_pos, projection_layer)

  for p in transformer.parameters():
    if p.dim() > 1:
      nn.init.xavier_uniform_(p)

  return transformer

